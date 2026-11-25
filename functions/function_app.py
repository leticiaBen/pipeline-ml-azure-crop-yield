"""
Pipeline evenementiel — section 4.3 de l'enonce.

UNE SEULE Function App contient les trois fonctions : sur le plan Flex
Consumption, un plan ne peut heberger qu'une seule application.

  dispatcher  declencheur Event Grid   valide le blob depose dans input/
  worker      declencheur file         appelle l'API, ecrit output/ et Cosmos
  recent      declencheur HTTP         GET /api/recent pour le tableau de bord

Aucun secret : les connexions passent par l'identite attribuee par le systeme
de la Function App (DefaultAzureCredential). Les reglages ne contiennent que
des noms de comptes et des URL.
"""

import datetime as dt
import hashlib
import json
import logging
import os
from urllib.parse import urlparse

import azure.functions as func
import requests
from azure.cosmos import CosmosClient
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from azure.storage.queue import (
    QueueClient,
    TextBase64DecodePolicy,
    TextBase64EncodePolicy,
)

# --- Reglages, tous par variables d'environnement ---------------------------
COMPTE_STOCKAGE = os.environ.get("STORAGE_ACCOUNT_NAME", "")
COSMOS_URL = os.environ.get("COSMOS_URL", "")
COSMOS_BASE = os.environ.get("COSMOS_DATABASE", "pipeline")
COSMOS_CONTENEUR = os.environ.get("COSMOS_CONTAINER", "inferences")
API_URL = os.environ.get("API_URL", "")
API_TIMEOUT = float(os.environ.get("API_TIMEOUT_S", "20"))
ORIGINE_SITE = os.environ.get("DASHBOARD_ORIGIN", "*")

FILE_ENTREE = "inference-requests"
TAILLE_MAX = int(os.environ.get("MAX_BLOB_BYTES", str(5 * 1024 * 1024)))
COLONNES_REQUISES = {"Area", "Item", "Year", "average_rain_fall_mm_per_year",
                     "pesticides_tonnes", "avg_temp"}

app = func.FunctionApp()

# --- Clients reutilises entre invocations -----------------------------------
# L'enonce exige un client HTTP reutilise. Les creer au niveau du module les
# partage entre les invocations d'une meme instance : on evite une poignee de
# main TLS par ligne de CSV. L'initialisation est paresseuse pour qu'une
# dependance indisponible ne fasse pas echouer le demarrage de l'application.
_identifiants = None
_blobs = None
_file = None
_cosmos = None
_session = None


def identifiants():
    global _identifiants
    if _identifiants is None:
        _identifiants = DefaultAzureCredential()
    return _identifiants


def blobs() -> BlobServiceClient:
    global _blobs
    if _blobs is None:
        _blobs = BlobServiceClient(
            f"https://{COMPTE_STOCKAGE}.blob.core.windows.net",
            credential=identifiants())
    return _blobs


def file_entree() -> QueueClient:
    """File d'entree, avec encodage Base64 OBLIGATOIRE.

    Le declencheur de file du runtime Functions attend du Base64 : sa
    configuration par defaut est MessageEncoding = Base64, visible dans les
    traces de demarrage de l'hote (QueuesOptions). Or le SDK
    azure-storage-queue n'encode RIEN par defaut.

    Sans ces deux politiques, le message part en texte brut, la liaison du
    worker echoue AVANT d'entrer dans le code utilisateur, et le message
    atteint maxDequeueCount en quelques secondes. Symptome trompeur : le
    message arrive en file poison sans qu'aucune trace du worker n'existe, ce
    qui laisse croire a un probleme de droits ou de reseau.
    """
    global _file
    if _file is None:
        _file = QueueClient(
            f"https://{COMPTE_STOCKAGE}.queue.core.windows.net",
            queue_name=FILE_ENTREE, credential=identifiants(),
            message_encode_policy=TextBase64EncodePolicy(),
            message_decode_policy=TextBase64DecodePolicy())
    return _file


def conteneur_cosmos():
    global _cosmos
    if _cosmos is None:
        _cosmos = (CosmosClient(COSMOS_URL, credential=identifiants())
                   .get_database_client(COSMOS_BASE)
                   .get_container_client(COSMOS_CONTENEUR))
    return _cosmos


def session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
    return _session


def maintenant() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


# ===========================================================================
#  dispatcher — declencheur Event Grid
# ===========================================================================
@app.function_name(name="dispatcher")
@app.event_grid_trigger(arg_name="evenement")
def dispatcher(evenement: func.EventGridEvent) -> None:
    """Valide le blob depose dans input/, puis met en file ou rejette.

    L'abonnement Event Grid est deja filtre sur Microsoft.Storage.BlobCreated
    et sur le prefixe du conteneur input/. On revalide tout de meme ici : un
    filtre d'abonnement peut etre modifie sans que le code le sache.
    """
    donnees = evenement.get_json()
    url = donnees.get("url", "")
    etag = (donnees.get("eTag") or "").strip('"')
    taille = int(donnees.get("contentLength") or 0)
    chemin = urlparse(url).path.lstrip("/")          # input/batch_001.csv
    conteneur, _, nom = chemin.partition("/")

    logging.info("dispatcher: %s (%d octets, etag %s)", chemin, taille, etag)

    motif = valider(conteneur, nom, taille)
    if motif:
        rejeter(nom, motif, taille, etag)
        logging.warning("dispatcher: %s rejete — %s", nom, motif)
        return

    message = {
        "blobName": nom,
        "eTag": etag,
        "size": taille,
        "enqueuedAt": maintenant(),
    }
    file_entree().send_message(json.dumps(message))
    logging.info("dispatcher: %s mis en file", nom)


def valider(conteneur: str, nom: str, taille: int) -> str | None:
    """Renvoie le motif de rejet, ou None si le fichier est acceptable."""
    if conteneur != "input":
        return f"conteneur inattendu: {conteneur}"
    if not nom.lower().endswith(".csv"):
        return f"extension non acceptee: {nom}"
    if taille == 0:
        return "fichier vide"
    if taille > TAILLE_MAX:
        return f"taille {taille} octets au-dela de la limite de {TAILLE_MAX}"

    # Verification du schema : on ne lit que l'en-tete, pas tout le fichier.
    try:
        client = blobs().get_blob_client("input", nom)
        entete = client.download_blob(offset=0, length=8192).readall()
        premiere = entete.decode("utf-8-sig", errors="replace").splitlines()[0]
    except Exception as e:
        return f"en-tete illisible: {type(e).__name__}"

    colonnes = {c.strip().strip('"') for c in premiere.split(",")}
    manquantes = COLONNES_REQUISES - colonnes
    if manquantes:
        return "colonnes manquantes: " + ", ".join(sorted(manquantes))
    return None


def rejeter(nom: str, motif: str, taille: int, etag: str) -> None:
    """Copie le blob dans rejected/ et y joint le motif.

    Le motif est pose en metadonnee ET dans un fichier .motif.json a cote :
    la metadonnee est propre, le fichier est visible dans le portail, ce qui
    rend la demonstration lisible.
    """
    source = blobs().get_blob_client("input", nom)
    cible = blobs().get_blob_client("rejected", nom)
    try:
        cible.start_copy_from_url(source.url, metadata={"motif": motif[:250]})
    except Exception as e:
        logging.error("rejeter: copie impossible pour %s: %s", nom, e)

    detail = {"blobName": nom, "motif": motif, "size": taille,
              "eTag": etag, "rejectedAt": maintenant()}
    blobs().get_blob_client("rejected", f"{nom}.motif.json").upload_blob(
        json.dumps(detail, ensure_ascii=False, indent=2).encode(),
        overwrite=True)


# ===========================================================================
#  worker — declencheur file d'attente
# ===========================================================================
@app.function_name(name="worker")
@app.queue_trigger(arg_name="message", queue_name=FILE_ENTREE,
                   connection="AzureWebJobsStorage")
def worker(message: func.QueueMessage) -> None:
    """Consomme la file, appelle l'API, ecrit output/ et Cosmos DB.

    IDEMPOTENCE — exigee par l'enonce. L'identifiant est derive du nom du
    blob ET de son ETag : deux depots du meme nom avec un contenu different
    produisent deux identifiants distincts, alors qu'une relivraison du meme
    message produit le meme. L'ecriture Cosmos est un upsert, et le blob de
    sortie est ecrit avec overwrite : rejouer un message ne cree pas de
    doublon.

    Les exceptions ne sont PAS rattrapees : c'est volontaire. Le runtime
    compte les echecs et, au 5e (maxDequeueCount dans host.json), deplace le
    message dans inference-requests-poison.
    """
    corps = json.loads(message.get_body().decode())
    nom = corps["blobName"]
    etag = corps.get("eTag", "")
    identifiant = hashlib.sha256(f"{nom}|{etag}".encode()).hexdigest()[:32]

    logging.info("worker: %s (essai %d, id %s)", nom,
                 message.dequeue_count, identifiant)

    contenu = blobs().get_blob_client("input", nom).download_blob().readall()
    lignes = lire_csv(contenu)
    if not lignes:
        raise ValueError(f"aucune ligne exploitable dans {nom}")

    debut = dt.datetime.now(dt.UTC)
    resultats = []
    erreurs = 0
    for i, ligne in enumerate(lignes):
        reponse = session().post(f"{API_URL}/predict", json=ligne,
                                 timeout=API_TIMEOUT)
        if reponse.status_code == 422:
            # Entree refusee par l'API : on leve pour que le runtime
            # reessaie puis envoie le message en file poison. C'est le
            # chemin du fichier empoisonne de l'enonce.
            raise ValueError(
                f"{nom} ligne {i + 1} refusee par l'API (422): "
                f"{reponse.text[:200]}")
        reponse.raise_for_status()
        p = reponse.json()
        resultats.append({
            "ligne": i + 1,
            "entree": ligne,
            # Rendement reel conserve s'il etait dans le CSV : il alimente la
            # courbe « predit contre reel » du tableau de bord (section 4.4).
            "reel": ligne.get("hg/ha_yield"),
            "predit": p["predicted_yield_hg_ha"],
            "modele": p["model_version"],
            "inference_ms": p.get("inference_ms"),
        })
    duree_ms = (dt.datetime.now(dt.UTC) - debut).total_seconds() * 1000

    sortie = {
        "id": identifiant,
        "fileName": nom,
        "eTag": etag,
        "processedAt": maintenant(),
        "rowCount": len(resultats),
        "errorCount": erreurs,
        "durationMs": round(duree_ms, 1),
        "modelVersion": resultats[0]["modele"] if resultats else None,
        "results": resultats,
    }
    blobs().get_blob_client("output", f"{nom}.json").upload_blob(
        json.dumps(sortie, ensure_ascii=False, indent=2).encode(),
        overwrite=True)

    # Cosmos ne recoit que les metadonnees, pas les resultats ligne par
    # ligne : le document reste petit et la facture en RU avec lui.
    predits = [r["predit"] for r in resultats]
    reels = [r["reel"] for r in resultats if r["reel"] is not None]
    conteneur_cosmos().upsert_item({
        "id": identifiant,
        "fileName": nom,
        "eTag": etag,
        "timestamp": sortie["processedAt"],
        "day": sortie["processedAt"][:10],
        "rowCount": len(resultats),
        "durationMs": sortie["durationMs"],
        "modelVersion": sortie["modelVersion"],
        "meanPredicted": round(sum(predits) / len(predits), 2) if predits else None,
        "meanActual": round(sum(reels) / len(reels), 2) if reels else None,
        "items": sorted({r["entree"].get("Item") for r in resultats if r["entree"].get("Item")}),
    })
    logging.info("worker: %s traite, %d lignes en %.0f ms",
                 nom, len(resultats), duree_ms)


def lire_csv(contenu: bytes) -> list[dict]:
    """Transforme le CSV en lignes typees pretes pour l'API."""
    import csv
    import io

    texte = contenu.decode("utf-8-sig", errors="replace")
    lignes = []
    for brute in csv.DictReader(io.StringIO(texte)):
        ligne = {}
        for cle, valeur in brute.items():
            if cle is None:
                continue
            cle = cle.strip()
            if cle in ("Area", "Item"):
                ligne[cle] = (valeur or "").strip()
            else:
                try:
                    ligne[cle] = float(valeur)
                except (TypeError, ValueError):
                    ligne[cle] = valeur
        if ligne.get("Area") and ligne.get("Item"):
            lignes.append(ligne)
    return lignes


# ===========================================================================
#  recent — declencheur HTTP, pour le tableau de bord (section 4.4)
# ===========================================================================
@app.function_name(name="recent")
@app.route(route="recent", methods=["GET", "OPTIONS"],
           auth_level=func.AuthLevel.ANONYMOUS)
def recent(req: func.HttpRequest) -> func.HttpResponse:
    """Les 20 dernieres inferences, en JSON, avec CORS limite au site.

    Le parametre DOIT s'appeler « req ». Contrairement a event_grid_trigger et
    queue_trigger, le decorateur @app.route n'accepte pas d'arg_name : il
    declare une liaison nommee « req » et le worker refuse d'indexer la
    fonction si le parametre porte un autre nom. L'erreur est
    « FunctionLoadError: the following parameters are declared in Python but
    not in the function definition », et elle fait echouer l'indexation des
    TROIS fonctions, pas seulement de celle-ci.
    """
    entetes = {
        "Access-Control-Allow-Origin": ORIGINE_SITE,
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Cache-Control": "no-store",
    }
    if req.method == "OPTIONS":
        return func.HttpResponse(status_code=204, headers=entetes)

    try:
        elements = list(conteneur_cosmos().query_items(
            query="SELECT TOP 20 c.id, c.fileName, c.timestamp, c.rowCount, "
                  "c.durationMs, c.modelVersion, c.meanPredicted, "
                  "c.meanActual, c.items FROM c ORDER BY c.timestamp DESC",
            enable_cross_partition_query=True))
    except Exception as e:
        logging.error("recent: %s", e)
        return func.HttpResponse(
            json.dumps({"error": type(e).__name__}), status_code=503,
            mimetype="application/json", headers=entetes)

    return func.HttpResponse(
        json.dumps({"count": len(elements), "items": elements},
                   ensure_ascii=False),
        mimetype="application/json", headers=entetes)
