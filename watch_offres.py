#!/usr/bin/env python3
"""
Surveille les nouvelles offres sur recrutement.education.gouv.fr
et envoie une notification ntfy pour chaque nouvelle offre détectée.

Variables d'environnement :
    NTFY_TOPIC   URL complète du topic ntfy (ex: https://ntfy.sh/mon-topic)
                 Peut aussi être définie directement dans NTFY_TOPIC ci-dessous.
"""

import json
import os
import sys
import requests
from datetime import datetime
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────────

STATE_FILE = Path(__file__).parent / "offres_seen.json"

# Topic ntfy — lu depuis l'env (secret GitHub), fallback sur la valeur ici
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "https://ntfy.sh/education-gouv-offres")

SEARCH_PARAMS = {
    "TERM": "",
    "ACD":  "",             # Académie (vide = toutes)
    "DF":   "",             # Domaine fonctionnel
    "NE":   "",             # Niveau d'études
    "REG":  "84",           # Région Auvergne-Rhône-Alpes
    "DPT":  "003;015;063",  # Allier, Cantal, Puy-de-Dôme
    "CAT":  "",
    "FNC":  "ENS",          # Filière Enseignement
    "NAT":  "",
}

BASE_OFFER_URL = "https://recrutement.education.gouv.fr/recrutement/offres"

API_URL = (
    "https://recrutement.education.gouv.fr"
    "/recrutement/webruntime/api/apex/execute"
    "?language=fr&asGuest=true&htmlEncode=false"
)

API_PAYLOAD = {
    "namespace": "",
    "classname": "@udd/01pIV000000aXE1",
    "method": "getData",
    "isContinuation": False,
    "cacheable": False,
    "params": {
        "name": "SearchOffresVirtuo",
        "input": SEARCH_PARAMS,
    },
}

HEADERS = {
    "Content-Type": "application/json; charset=utf-8",
    "Accept": "*/*",
    "Origin": "https://recrutement.education.gouv.fr",
    "Referer": "https://recrutement.education.gouv.fr/recrutement/offres",
}

# ── Persistance ────────────────────────────────────────────────────────────────

def load_seen_ids() -> set:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen_ids(ids: set) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(sorted(ids), f, indent=2)

# ── API ────────────────────────────────────────────────────────────────────────

def fetch_offres() -> list[dict]:
    resp = requests.post(API_URL, json=API_PAYLOAD, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json().get("returnValue", [])

# ── Notification ───────────────────────────────────────────────────────────────

def notify(offre: dict) -> None:
    offer_id  = offre["Id"]
    name      = offre.get("Name", "Offre sans titre")
    dept      = offre.get("Departement__c", "?")
    pub_date  = offre.get("PublicationDateDebutParDefautFormula__c", "")
    employeur = offre.get("EmployeurNameFormula__c", "")
    nat       = offre.get("NatureContrat__c", "")
    url       = f"{BASE_OFFER_URL}/{offer_id}"

    title   = f"[{dept}] {nat} — {name[:80]}"
    message = f"{pub_date}\n{employeur}\n{url}"

    try:
        r = requests.post(
            NTFY_TOPIC,
            data=message.encode("utf-8"),
            headers={
                "Title":    title.encode("utf-8"),
                "Priority": "default",
                "Tags":     "school",
            },
            timeout=10,
        )
        r.raise_for_status()
        print(f"  ✓ ntfy : {name[:70]}")
    except Exception as e:
        print(f"  ✗ Erreur ntfy : {e}", file=sys.stderr)

# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    is_first_run = not STATE_FILE.exists()

    if is_first_run:
        print(f"[{ts}] Premier lancement — initialisation de la baseline (pas de notification)...")
    else:
        print(f"[{ts}] Vérification des offres...")

    seen_ids = load_seen_ids()

    try:
        offres = fetch_offres()
    except Exception as e:
        print(f"Erreur récupération : {e}", file=sys.stderr)
        sys.exit(1)

    print(f"  {len(offres)} offre(s) trouvée(s)")

    if is_first_run:
        for offre in offres:
            seen_ids.add(offre["Id"])
        save_seen_ids(seen_ids)
        print(f"  Baseline enregistrée ({len(seen_ids)} IDs). Les prochains runs notifieront uniquement les nouvelles offres.")
        return

    new_offres = [o for o in offres if o["Id"] not in seen_ids]
    print(f"  {len(new_offres)} nouvelle(s)")

    for offre in new_offres:
        notify(offre)
        seen_ids.add(offre["Id"])

    save_seen_ids(seen_ids)

    if not new_offres:
        print("  Rien de nouveau.")


if __name__ == "__main__":
    main()
