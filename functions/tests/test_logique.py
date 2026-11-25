"""
Tests de la logique pure du pipeline : validation et lecture CSV.

Le runtime Functions n'est pas necessaire ici — et c'est l'interet. Ces
fonctions sont celles qui decident d'accepter ou de rejeter un fichier, donc
celles ou une erreur coute le plus cher.
"""

import hashlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import function_app as fa  # noqa: E402

RACINE = pathlib.Path(__file__).resolve().parents[2]


# --- valider() : les rejets qui n'exigent aucun acces reseau ---------------
def test_rejet_mauvais_conteneur():
    assert "conteneur inattendu" in fa.valider("output", "x.csv", 100)


def test_rejet_mauvaise_extension():
    assert "extension non acceptee" in fa.valider("input", "notes.txt", 100)


def test_rejet_fichier_vide():
    assert fa.valider("input", "vide.csv", 0) == "fichier vide"


def test_rejet_trop_gros():
    motif = fa.valider("input", "gros.csv", fa.TAILLE_MAX + 1)
    assert "au-dela de la limite" in motif


# --- valider() : verification du schema, avec le blob simule --------------
class _FauxBlob:
    def __init__(self, entete: bytes):
        self._entete = entete

    def download_blob(self, offset=0, length=None):
        class _Flux:
            def __init__(self, d):
                self._d = d

            def readall(self):
                return self._d
        return _Flux(self._entete)


class _FauxService:
    def __init__(self, entete: bytes):
        self._entete = entete

    def get_blob_client(self, conteneur, nom):
        return _FauxBlob(self._entete)


def test_schema_complet_accepte(monkeypatch):
    entete = (b"Area,Item,Year,average_rain_fall_mm_per_year,"
              b"pesticides_tonnes,avg_temp,hg/ha_yield\n")
    monkeypatch.setattr(fa, "blobs", lambda: _FauxService(entete))
    assert fa.valider("input", "ok.csv", 500) is None


def test_colonne_manquante_rejetee(monkeypatch):
    # avg_temp absente : c'est exactement samples/invalid/colonne_manquante.csv
    entete = (b"Area,Item,Year,average_rain_fall_mm_per_year,"
              b"pesticides_tonnes,hg/ha_yield\n")
    monkeypatch.setattr(fa, "blobs", lambda: _FauxService(entete))
    motif = fa.valider("input", "ko.csv", 500)
    assert "colonnes manquantes" in motif and "avg_temp" in motif


def test_bom_utf8_ne_casse_pas_le_schema(monkeypatch):
    """Excel prefixe ses CSV d'un BOM. Sans utf-8-sig, la premiere colonne
    s'appellerait « ﻿Area » et le fichier serait rejete a tort."""
    entete = "﻿Area,Item,Year,average_rain_fall_mm_per_year,pesticides_tonnes,avg_temp\n".encode()
    monkeypatch.setattr(fa, "blobs", lambda: _FauxService(entete))
    assert fa.valider("input", "excel.csv", 500) is None


# --- lire_csv() : sur un vrai lot du depot --------------------------------
def test_lire_csv_sur_un_vrai_lot():
    contenu = (RACINE / "samples" / "valid" / "batch_001.csv").read_bytes()
    lignes = fa.lire_csv(contenu)
    assert len(lignes) == 25
    p = lignes[0]
    assert isinstance(p["Area"], str) and isinstance(p["Item"], str)
    # Les colonnes numeriques doivent etre converties, sinon Pydantic les
    # refuserait cote API.
    for cle in ("Year", "average_rain_fall_mm_per_year", "pesticides_tonnes", "avg_temp"):
        assert isinstance(p[cle], float), cle


def test_lire_csv_conserve_le_rendement_reel():
    contenu = (RACINE / "samples" / "valid" / "batch_001.csv").read_bytes()
    lignes = fa.lire_csv(contenu)
    assert all("hg/ha_yield" in p for p in lignes)


def test_lire_csv_ignore_les_lignes_incompletes():
    contenu = b"Area,Item,Year,avg_temp\n,Maize,2010,12\nFrance,,2010,12\nFrance,Maize,2010,12\n"
    assert len(fa.lire_csv(contenu)) == 1


def test_lire_csv_sur_le_fichier_empoisonne():
    """Le fichier empoisonne doit se LIRE sans probleme : c'est l'API qui le
    refuse, pas le worker. Sinon le message n'atteindrait jamais la file
    poison par le chemin prevu."""
    contenu = (RACINE / "samples" / "poison" / "pluie_negative.csv").read_bytes()
    lignes = fa.lire_csv(contenu)
    assert len(lignes) == 5
    assert all(p["average_rain_fall_mm_per_year"] == -500 for p in lignes)


# --- idempotence ----------------------------------------------------------
def _identifiant(nom, etag):
    return hashlib.sha256(f"{nom}|{etag}".encode()).hexdigest()[:32]


def test_identifiant_stable_pour_le_meme_blob():
    assert _identifiant("b.csv", "0x1") == _identifiant("b.csv", "0x1")


def test_identifiant_change_si_le_contenu_change():
    """Meme nom, ETag different : c'est un nouveau contenu, donc un nouveau
    document. Sans l'ETag, un redepot ecraserait silencieusement le premier
    resultat."""
    assert _identifiant("b.csv", "0x1") != _identifiant("b.csv", "0x2")


# --- interoperabilite avec le declencheur de file -------------------------
def test_la_politique_base64_encode_bien():
    """Verifie le mecanisme lui-meme, independamment de notre code."""
    import base64

    from azure.storage.queue import TextBase64EncodePolicy

    clair = '{"blobName": "x.csv"}'
    assert TextBase64EncodePolicy().encode(clair) == base64.b64encode(
        clair.encode()).decode()


def test_la_file_est_configuree_en_base64(monkeypatch):
    """Le declencheur Functions attend du Base64 : sa configuration par defaut
    est MessageEncoding = Base64, visible dans les traces QueuesOptions de
    l'hote. Le SDK azure-storage-queue, lui, n'encode rien par defaut.

    Sans ces politiques, le message part en texte brut, la liaison du worker
    echoue AVANT le code utilisateur, et le message atteint maxDequeueCount en
    quelques secondes — sans laisser une seule trace du worker. C'est un bug
    tres couteux a diagnostiquer, d'ou ce test.

    On inspecte des attributs prives du client : c'est assume, le SDK n'expose
    pas ces politiques autrement."""
    from azure.core.credentials import AzureSasCredential
    from azure.storage.queue import TextBase64DecodePolicy, TextBase64EncodePolicy

    monkeypatch.setattr(fa, "identifiants",
                        lambda: AzureSasCredential("sv=2020-01-01&sig=factice"))
    monkeypatch.setattr(fa, "COMPTE_STOCKAGE", "comptefactice")
    monkeypatch.setattr(fa, "_file", None)

    client = fa.file_entree()
    assert isinstance(client._message_encode_policy, TextBase64EncodePolicy)
    assert isinstance(client._message_decode_policy, TextBase64DecodePolicy)
    fa._file = None
