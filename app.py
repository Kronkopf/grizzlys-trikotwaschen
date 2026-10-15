import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from PIL import Image
import json
import base64
import requests
import os
from datetime import datetime
import plotly.express as px
import pandas as pd
import cloudinary
import cloudinary.uploader
import io

# ── Konfiguration aus Streamlit Secrets ───────────────────────────────────────
try:
    OPENROUTER_API_KEY    = st.secrets["OPENROUTER_API_KEY"]
    CLOUDINARY_CLOUD_NAME = st.secrets["CLOUDINARY_CLOUD_NAME"]
    CLOUDINARY_API_KEY    = st.secrets["CLOUDINARY_API_KEY"]
    CLOUDINARY_API_SECRET = st.secrets["CLOUDINARY_API_SECRET"]
    SHEET_NAME            = st.secrets["SHEET_NAME"]
except KeyError as e:
    st.error(f"Secret fehlt: {e}")
    st.write("Verfuegbare Secrets:", list(st.secrets.keys()))
    st.stop()

cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET,
)

MODELLE = [
    "qwen/qwen3-vl-32b-instruct",       # Bestes Vision-Modell 2026
    "google/gemini-2.5-flash",           # Google Fallback
    "meta-llama/llama-4-maverick",       # Fallback 3
    "qwen/qwen2.5-vl-72b-instruct",     # Letzter Ausweg
]

FARBEN = ["Alle", "Rot", "Blau", "Gruen", "Gelb", "Gold", "Schwarz", "Weiss", "Silber", "Braun", "Orange", "Lila"]

FARB_MAP = {
    "Rot": "#E53935", "Blau": "#1E88E5", "Gruen": "#43A047",
    "Gelb": "#FDD835", "Gold": "#FFB300", "Schwarz": "#212121",
    "Weiss": "#F5F5F5", "Silber": "#9E9E9E", "Braun": "#6D4C41",
    "Orange": "#FB8C00", "Lila": "#8E24AA",
}

LAND_ISO = {
    "Deutschland": "DEU", "Österreich": "AUT", "Schweiz": "CHE",
    "Frankreich": "FRA", "Italien": "ITA", "Spanien": "ESP",
    "Portugal": "PRT", "Niederlande": "NLD", "Belgien": "BEL",
    "Luxemburg": "LUX", "Dänemark": "DNK", "Schweden": "SWE",
    "Norwegen": "NOR", "Finnland": "FIN", "Polen": "POL",
    "Tschechien": "CZE", "Slowakei": "SVK", "Ungarn": "HUN",
    "Rumänien": "ROU", "Bulgarien": "BGR", "Kroatien": "HRV",
    "Slowenien": "SVN", "Serbien": "SRB", "Griechenland": "GRC",
    "Türkei": "TUR", "Russland": "RUS", "Ukraine": "UKR",
    "Irland": "IRL", "Grossbritannien": "GBR", "England": "GBR",
    "Schottland": "GBR", "Vereinigtes Königreich": "GBR", "Island": "ISL",
    "USA": "USA", "Vereinigte Staaten": "USA", "Kanada": "CAN",
    "Mexiko": "MEX", "Brasilien": "BRA", "Argentinien": "ARG",
    "Chile": "CHL", "Kolumbien": "COL", "Kuba": "CUB",
    "China": "CHN", "Japan": "JPN", "Südkorea": "KOR",
    "Vietnam": "VNM", "Thailand": "THA", "Indonesien": "IDN",
    "Philippinen": "PHL", "Indien": "IND", "Sri Lanka": "LKA",
    "Malaysia": "MYS", "Singapur": "SGP", "Taiwan": "TWN",
    "Mongolei": "MNG", "Kasachstan": "KAZ", "Israel": "ISR",
    "Libanon": "LBN", "Saudi-Arabien": "SAU", "Irak": "IRQ",
    "Iran": "IRN", "Ägypten": "EGY", "Marokko": "MAR",
    "Tunesien": "TUN", "Algerien": "DZA", "Äthiopien": "ETH",
    "Kenia": "KEN", "Nigeria": "NGA", "Ghana": "GHA",
    "Südafrika": "ZAF", "Tansania": "TZA", "Kamerun": "CMR",
    "Senegal": "SEN", "Angola": "AGO", "Kongo": "COD",
    "Australien": "AUS", "Neuseeland": "NZL",
    "Litauen": "LTU", "Lettland": "LVA", "Estland": "EST",
    "Belarus": "BLR", "Moldau": "MDA", "Georgien": "GEO",
    "Armenien": "ARM", "Aserbaidschan": "AZE", "Zypern": "CYP",
    "Malta": "MLT", "Albanien": "ALB", "Montenegro": "MNE",
    "Bosnien": "BIH", "Nordmazedonien": "MKD", "Kosovo": "XKX",
}

# ── Google Sheets ─────────────────────────────────────────────────────────────
@st.cache_resource
def get_sheet_client():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    )
    return gspread.authorize(creds)

def connect_to_sheet():
    try:
        return get_sheet_client().open(SHEET_NAME).sheet1
    except Exception as e:
        st.error(f"Google Sheets Fehler: {e}")
        return None

def lade_sammlung_frisch():
    sheet = connect_to_sheet()
    if not sheet:
        return []
    sammlung = []
    for idx, e in enumerate(sheet.get_all_records()):
        vals = list(e.values())
        bild_url = str(vals[4]).strip() if len(vals) > 4 else ""
        sammlung.append({
            "row":          idx + 2,
            "reihenfolge":  idx,
            "brauerei":     str(vals[0]).strip() if len(vals) > 0 else "",
            "getraenk":     str(vals[1]).strip() if len(vals) > 1 else "",
            "land":         str(vals[2]).strip() if len(vals) > 2 else "",
            "beschreibung": str(vals[3]).strip() if len(vals) > 3 else "",
            "bild_url":     bild_url,
            "farbe":        str(vals[5]).strip() if len(vals) > 5 else "",
            "verifiziert":  str(vals[6]).strip() if len(vals) > 6 else "",
        })
    return sammlung

def get_sammlung():
    if st.session_state.sammlung is None:
        st.session_state.sammlung = lade_sammlung_frisch()
    return st.session_state.sammlung

def invalidiere_cache():
    st.session_state.sammlung = None

# ── Cloudinary Bild hochladen ─────────────────────────────────────────────────
def lade_bild_zu_cloudinary(uploaded_file, brauerei):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe = "".join(c for c in brauerei if c.isalnum() or c in (" ", "-", "_")).strip().replace(" ", "_")[:30]
    public_id = f"kronkorken/{safe}_{timestamp}"

    img = Image.open(uploaded_file).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    buf.seek(0)

    result = cloudinary.uploader.upload(
        buf,
        public_id=public_id,
        overwrite=False,
        resource_type="image",
    )
    return result["secure_url"]

# ── KI-Analyse ────────────────────────────────────────────────────────────────
def encode_image_bytes(uploaded_file):
    try:
        uploaded_file.seek(0)
        raw = uploaded_file.read()
        uploaded_file.seek(0)
        from PIL import Image as PILImage
        import io as _io
        buf_in = _io.BytesIO(raw)
        img = PILImage.open(buf_in).convert("RGB")
        buf_out = _io.BytesIO()
        img.save(buf_out, format="JPEG", quality=85)
        buf_out.seek(0)
        return base64.b64encode(buf_out.read()).decode("utf-8")
    except Exception as e:
        raise Exception(f"Bild-Encoding fehlgeschlagen: {type(e).__name__}: {e}")

def analyse_kronkorken(uploaded_file):
    b64 = encode_image_bytes(uploaded_file)
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://kronkorken.streamlit.app",
        "X-Title": "Kronkorken Scanner"
    }
    prompt = (
        "Du bist ein weltweit führender Experte für Biermarken, Brauereien und Kronkorken. "
        "Auf dem Bild ist genau EIN Kronkorken zu sehen.\n\n"
        "Gehe in folgenden Schritten vor:\n"
        "1. Beschreibe alle sichtbaren Details: Farben, Texte, Logos, Symbole, Zahlen\n"
        "2. Welche Brauerei oder Marke passt zu diesen Merkmalen? "
        "Denke auch an wenig bekannte internationale Brauereien.\n"
        "3. In welchem Land wird dieses Bier gebraut?\n\n"
        "Gib das Ergebnis AUSSCHLIESSLICH als valides JSON-Objekt zurueck, kein Markdown:\n"
        "{\"brauerei\": \"Exakter Brauereiname\", "
        "\"getraenk\": \"Bier oder Kein Bier\", "
        "\"land\": \"Herkunftsland auf Deutsch\", "
        "\"beschreibung\": \"Kurze visuelle Beschreibung\", "
        "\"farbe\": \"Hauptfarbe auf Deutsch z.B. Rot Blau Gruen Gelb Gold Schwarz Weiss Silber Braun Orange Lila\"}\n\n"
        "brauerei=nur Markenname ohne Biersorten, getraenk=nur Bier oder Kein Bier, "
        "land=auf Deutsch, farbe=ein Wort"
    )
    last_error = "Kein Modell verfuegbar"
    for modell in MODELLE:
        payload = {
            "model": modell,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            ]}],
            "temperature": 0.0,
            "max_tokens": 500
        }
        try:
            res = requests.post("https://openrouter.ai/api/v1/chat/completions",
                                headers=headers, json=payload, timeout=60)
            res_json = res.json()
            if "error" in res_json:
                last_error = f"Modell {modell}: {res_json['error'].get('message', str(res_json['error']))}"
                continue
            if "choices" not in res_json:
                last_error = f"Modell {modell}: Keine choices in Antwort: {str(res_json)[:200]}"
                continue
            raw = res_json["choices"][0]["message"]["content"].strip()
            if "{" in raw:
                raw = raw[raw.index("{"):raw.rindex("}")+1]
            result = json.loads(raw)
            g = result.get("getraenk", "Bier")
            result["getraenk"] = "Kein Bier" if "kein" in g.lower() else "Bier"
            return result, None
        except json.JSONDecodeError as e:
            last_error = f"Modell {modell}: JSON Fehler: {e}"
            continue
        except Exception as e:
            last_error = f"Modell {modell}: {type(e).__name__}: {str(e)}"
            continue
    return None, f"Alle Modelle fehlgeschlagen. Letzter Fehler: {last_error}"

# ── Sheet schreiben ───────────────────────────────────────────────────────────
def schreibe_in_sheet(sheet, b, g, l, desc, bild_url, farbe):
    import time
    for versuch in range(3):
        try:
            sheet.append_row([b, g, l, desc, bild_url, farbe])
            return
        except Exception as e:
            if versuch < 2:
                time.sleep(5)
            else:
                raise e

def aktualisiere_zeile(sheet, row, b, g, l, desc, bild_url, farbe):
    # Alles in einem einzigen Batch-Call
    sheet.update(f"A{row}:F{row}", [[b, g, l, desc, bild_url, farbe]])

def setze_verifiziert(sheet, row):
    sheet.update(f"G{row}", [["✅"]])

def setze_unverifiziert(sheet, row):
    sheet.update(f"G{row}", [[""]])

def rescan_brauerei_land(bild_url):
    """Nur Brauerei und Land neu erkennen."""
    import requests as req, json, base64, io
    from PIL import Image as PILImage
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://kronkorken.streamlit.app",
        "X-Title": "Kronkorken Scanner"
    }
    prompt = (
        "Du bist ein Experte fuer Biermarken. Auf dem Bild ist ein Kronkorken. "
        "Erkenne NUR die Brauerei/Marke und das Herkunftsland. "
        "Antworte AUSSCHLIESSLICH als valides JSON ohne Markdown: "
        "{\"brauerei\": \"Name\", \"land\": \"Land auf Deutsch\"}"
    )
    # Bild von Cloudinary laden und kodieren
    try:
        img_res = req.get(bild_url, timeout=15)
        buf_in = io.BytesIO(img_res.content)
        img = PILImage.open(buf_in).convert("RGB")
        buf_out = io.BytesIO()
        img.save(buf_out, format="JPEG", quality=85)
        buf_out.seek(0)
        b64 = base64.b64encode(buf_out.read()).decode("utf-8")
    except Exception as e:
        return None, f"Bild laden fehlgeschlagen: {e}"

    last_error = "Kein Modell"
    for modell in MODELLE:
        payload = {
            "model": modell,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            ]}],
            "temperature": 0.0,
            "max_tokens": 100
        }
        try:
            res = req.post("https://openrouter.ai/api/v1/chat/completions",
                           headers=headers, json=payload, timeout=60)
            res_json = res.json()
            if "error" in res_json:
                last_error = res_json["error"].get("message", str(res_json["error"]))
                continue
            raw = res_json["choices"][0]["message"]["content"].strip()
            if "{" in raw:
                raw = raw[raw.index("{"):raw.rindex("}")+1]
            result = json.loads(raw)
            return result, None
        except Exception as e:
            last_error = str(e)
            continue
    return None, last_error

def loesche_zeile(sheet, row):
    sheet.delete_rows(row)

# ── Session State ─────────────────────────────────────────────────────────────
for key, default in [
    ("sammlung", None),
    ("scan_queue", []),
    ("pending", None),
    ("scan_results", []),
    ("edit_rows", {}),
]:
    if key not in st.session_state:
        st.session_state[key] = default

st.set_page_config(page_title="Kronkorken Scanner", page_icon="🍺", layout="wide")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    sammlung_alle = get_sammlung()
    st.markdown("### 📊 Übersicht")
    s = sammlung_alle
    if s:
        c1, c2 = st.columns(2)
        c1.metric("Gesamt", len(s))
        c2.metric("Bier", sum(1 for e in s if e["getraenk"] == "Bier"))
        c3, c4 = st.columns(2)
        c3.metric("Kein Bier", sum(1 for e in s if e["getraenk"] != "Bier"))
        c4.metric("Länder", len(set(e["land"] for e in s if e["land"] and e["land"].lower() != "unbekannt")))
        st.metric("Brauereien", len(set(e["brauerei"] for e in s if e["brauerei"] and e["brauerei"].lower() != "unbekannt")))

    st.markdown("---")
    st.markdown("### 🔍 Filter & Sortierung")

    alle_brauereien = sorted(set(e["brauerei"] for e in sammlung_alle if e["brauerei"] and e["brauerei"].lower() != "unbekannt"))
    alle_laender    = sorted(set(e["land"]     for e in sammlung_alle if e["land"]     and e["land"].lower()     != "unbekannt"))

    suche      = st.text_input("🔎 Suchen", placeholder="Stichwort...")
    filter_b   = st.selectbox("🏭 Brauerei", ["Alle"] + alle_brauereien)
    filter_l   = st.selectbox("🌍 Land",     ["Alle"] + alle_laender)
    filter_g   = st.selectbox("🍺 Getränk",  ["Alle", "Bier", "Kein Bier"])
    filter_f   = st.selectbox("🎨 Farbe",    FARBEN)
    sortierung = st.selectbox("📋 Sortierung", [
        "Zuletzt hinzugefuegt", "Aelteste zuerst",
        "Brauerei A-Z", "Brauerei Z-A", "Land A-Z", "Farbe A-Z"
    ])
    st.markdown("---")
    if st.button("🔄 Sammlung neu laden", width="stretch"):
        invalidiere_cache()
        st.rerun()

tab_scan, tab_galerie, tab_stats, tab_rescan = st.tabs(["📷 Scanner", "🖼️ Meine Sammlung", "📊 Statistiken", "🔄 Re-Scan"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB SCANNER
# ══════════════════════════════════════════════════════════════════════════════
with tab_scan:
    st.title("📷 Kronkorken Scanner")

    if st.session_state.pending:
        p = st.session_state.pending
        st.warning(f"### ⚠️ Mögliche Dublette: **{p['brauerei']}** ({p['land']})")
        vorhandene = [e for e in get_sammlung()
                      if e["brauerei"].lower() == p["brauerei"].lower()
                      and e["farbe"].lower() == p["farbe"].lower()]
        col_neu, col_alt = st.columns(2)
        with col_neu:
            st.markdown("**Neues Foto**")
            st.image(p["bild_vorschau"], width="stretch")
            st.caption(f"{p['beschreibung']} · {p['farbe']}")
        with col_alt:
            st.markdown(f"**Bereits in Sammlung ({len(vorhandene)} Einträge)**")
            if vorhandene:
                for zeile_start in range(0, len(vorhandene), 4):
                    zeile = vorhandene[zeile_start:zeile_start+4]
                    cols_alt = st.columns(len(zeile))
                    for idx, match in enumerate(zeile):
                        with cols_alt[idx]:
                            if match["bild_url"] and match["bild_url"].startswith("http"):
                                st.image(match["bild_url"])
                            else:
                                st.markdown("🍺")
                            st.caption(f"🎨 {match['farbe']}")
                            st.caption(match["beschreibung"])
        col_ja, col_nein = st.columns(2)
        with col_ja:
            if st.button("✅ Neu speichern – anderer Kronkorken", type="primary", width="stretch"):
                sheet = connect_to_sheet()
                if sheet:
                    p["uploaded_file"].seek(0)
                    bild_url = lade_bild_zu_cloudinary(p["uploaded_file"], p["brauerei"])
                    schreibe_in_sheet(sheet, p["brauerei"], p["getraenk"], p["land"], p["beschreibung"], bild_url, p["farbe"])
                    invalidiere_cache()
                st.session_state.scan_results.append(("neu", p["brauerei"], p["land"]))
                st.session_state.pending = None
                st.rerun()
        with col_nein:
            if st.button("🚫 Überspringen – Dublette", width="stretch"):
                st.session_state.scan_results.append(("dublette", p["brauerei"], p["land"]))
                st.session_state.pending = None
                st.rerun()
        st.stop()

    # API Test
    with st.expander("🔧 API Test"):
        if st.button("OpenRouter API testen"):
            import requests as req
            try:
                test_res = req.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://kronkorken.streamlit.app",
                    },
                    json={
                        "model": MODELLE[0],
                        "messages": [{"role": "user", "content": "Say hello in one word"}],
                        "max_tokens": 10,
                    },
                    timeout=30
                )
                st.write("Status:", test_res.status_code)
                st.write("Antwort:", test_res.json())
            except Exception as e:
                st.error(f"Verbindungsfehler: {e}")

    uploaded_files = st.file_uploader(
        "Fotos hochladen — auch direkt vom Handy per Kamera möglich",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True
    )
    if uploaded_files:
        st.info(f"{len(uploaded_files)} Foto(s) ausgewählt.")
        if st.button("Alle scannen", type="primary"):
            get_sammlung()
            st.session_state.scan_queue = list(uploaded_files)
            st.session_state.scan_results = []
            st.session_state.pending = None
            st.rerun()

    if st.session_state.scan_queue:
        sammlung = get_sammlung()
        sheet = connect_to_sheet()
        exist_set = set(
            (e["brauerei"].lower(), e["farbe"].lower())
            for e in sammlung
        )
        for r in st.session_state.scan_results:
            if r[0] == "neu":
                farbe_r = r[3].lower() if len(r) > 3 else ""
                exist_set.add((r[1].lower(), farbe_r))

        uploaded_file = st.session_state.scan_queue[0]
        idx = len(st.session_state.scan_results)
        gesamt = idx + len(st.session_state.scan_queue)

        with st.spinner(f"Analysiere {idx+1}/{gesamt}: {uploaded_file.name} …"):
            uploaded_file.seek(0)
            result, fehler_msg = analyse_kronkorken(uploaded_file)

        if fehler_msg:
            st.error(f"Fehler bei {uploaded_file.name}: {fehler_msg}")
            st.session_state.scan_results.append(("fehler", uploaded_file.name, ""))
            st.session_state.scan_queue.pop(0)
            st.rerun()
        else:
            b     = result.get("brauerei", "Unbekannt").strip()
            g     = result.get("getraenk", "Bier").strip()
            l     = result.get("land", "Unbekannt").strip()
            desc  = result.get("beschreibung", "").strip()
            farbe = result.get("farbe", "").strip()

            uploaded_file.seek(0)
            vorschau = Image.open(uploaded_file)

            if (b.lower(), farbe.lower()) in exist_set:
                st.session_state.pending = {
                    "brauerei": b, "getraenk": g, "land": l,
                    "beschreibung": desc, "farbe": farbe,
                    "uploaded_file": uploaded_file,
                    "bild_vorschau": vorschau,
                }
                st.session_state.scan_queue.pop(0)
                st.rerun()
            else:
                with st.spinner(f"Lade Bild zu Cloudinary hoch …"):
                    uploaded_file.seek(0)
                    bild_url = lade_bild_zu_cloudinary(uploaded_file, b)
                if sheet:
                    schreibe_in_sheet(sheet, b, g, l, desc, bild_url, farbe)
                exist_set.add((b.lower(), farbe.lower()))
                st.session_state.scan_results.append(("neu", b, l, farbe))
                if st.session_state.sammlung is not None:
                    st.session_state.sammlung.append({
                        "row": len(st.session_state.sammlung) + 2,
                        "reihenfolge": len(st.session_state.sammlung),
                        "brauerei": b, "getraenk": g, "land": l,
                        "beschreibung": desc, "bild_url": bild_url, "farbe": farbe,
                    })
                st.session_state.scan_queue.pop(0)
                st.rerun()

    if st.session_state.scan_results and not st.session_state.scan_queue and not st.session_state.pending:
        st.markdown("---")
        neu_list = [r for r in st.session_state.scan_results if r[0] == "neu"]
        dub_list = [r for r in st.session_state.scan_results if r[0] == "dublette"]
        err_list = [r for r in st.session_state.scan_results if r[0] == "fehler"]
        c1, c2, c3 = st.columns(3)
        c1.metric("✅ Neu gespeichert", len(neu_list))
        c2.metric("🚫 Dubletten", len(dub_list))
        c3.metric("❌ Fehler", len(err_list))
        for r in neu_list: st.success(f"✅ {r[1]} ({r[2]})")
        for r in dub_list: st.warning(f"🚫 Dublette: {r[1]} ({r[2]})")
        for r in err_list: st.error(f"❌ Fehler: {r[1]}")
        if neu_list: st.balloons()

# ══════════════════════════════════════════════════════════════════════════════
# TAB GALERIE
# ══════════════════════════════════════════════════════════════════════════════
with tab_galerie:
    st.title("🖼️ Meine Kronkorken-Sammlung")

    sammlung = list(sammlung_alle)
    if suche:
        s_lower = suche.lower()
        sammlung = [e for e in sammlung if s_lower in e["brauerei"].lower() or s_lower in e["land"].lower() or s_lower in e["beschreibung"].lower()]
    if filter_b != "Alle": sammlung = [e for e in sammlung if e["brauerei"] == filter_b]
    if filter_l != "Alle": sammlung = [e for e in sammlung if e["land"]     == filter_l]
    if filter_g != "Alle": sammlung = [e for e in sammlung if e["getraenk"] == filter_g]
    if filter_f != "Alle": sammlung = [e for e in sammlung if filter_f.lower() in e["farbe"].lower()]

    if sortierung == "Zuletzt hinzugefuegt":
        sammlung.sort(key=lambda x: x["reihenfolge"], reverse=True)
    elif sortierung == "Aelteste zuerst":
        sammlung.sort(key=lambda x: x["reihenfolge"])
    elif sortierung == "Brauerei A-Z":
        sammlung.sort(key=lambda x: x["brauerei"].lower())
    elif sortierung == "Brauerei Z-A":
        sammlung.sort(key=lambda x: x["brauerei"].lower(), reverse=True)
    elif sortierung == "Land A-Z":
        sammlung.sort(key=lambda x: x["land"].lower())
    elif sortierung == "Farbe A-Z":
        sammlung.sort(key=lambda x: x["farbe"].lower())

    st.write(f"**{len(sammlung)} Kronkorken** gefunden")
    st.markdown("---")

    @st.fragment
    def karte(eintrag):
        row_key = eintrag["row"]
        bild = eintrag["bild_url"]
        if bild and bild.startswith("http"):
            st.image(bild, use_container_width=True)
        else:
            st.markdown("<div style='background:#f0f0f0;height:120px;display:flex;align-items:center;justify-content:center;border-radius:8px;font-size:36px'>🍺</div>", unsafe_allow_html=True)
        st.markdown(f"**{eintrag['brauerei']}**")
        st.caption(f"{eintrag['land']} · {eintrag['getraenk']}")
        if eintrag["farbe"]:
            st.caption(f"🎨 {eintrag['farbe']}")
        ist_verifiziert = eintrag.get("verifiziert", "") == "✅"
        st.caption("✅ Verifiziert" if ist_verifiziert else "⬜ Nicht verifiziert")

        col_ver, col_edit, col_del = st.columns(3)
        with col_ver:
            ver_label = "↩️" if ist_verifiziert else "✅"
            if st.button(ver_label, key=f"ver_{row_key}", use_container_width=True):
                for e in st.session_state.sammlung:
                    if e["row"] == row_key:
                        e["verifiziert"] = "" if ist_verifiziert else "✅"
                        eintrag["verifiziert"] = e["verifiziert"]
                        break
                sheet = connect_to_sheet()
                if sheet:
                    if ist_verifiziert:
                        setze_unverifiziert(sheet, row_key)
                    else:
                        setze_verifiziert(sheet, row_key)
                st.toast("✅ Verifiziert!" if not ist_verifiziert else "↩️ Zurückgesetzt")
                st.rerun(scope="fragment")
        with col_edit:
            label = "🔒" if st.session_state.edit_rows.get(row_key) else "✏️"
            if st.button(label, key=f"edit_{row_key}", use_container_width=True):
                st.session_state.edit_rows[row_key] = not st.session_state.edit_rows.get(row_key, False)
                st.rerun(scope="fragment")
        with col_del:
            if st.button("🗑️", key=f"del_{row_key}", use_container_width=True):
                sheet = connect_to_sheet()
                if sheet:
                    loesche_zeile(sheet, row_key)
                    invalidiere_cache()
                    st.rerun(scope="app")

        if st.session_state.edit_rows.get(row_key):
            with st.form(key=f"form_{row_key}"):
                neu_b    = st.text_input("Brauerei",    value=eintrag["brauerei"])
                neu_l    = st.text_input("Land",        value=eintrag["land"])
                neu_g    = st.selectbox("Getränk", ["Bier", "Kein Bier"],
                                        index=0 if eintrag["getraenk"] == "Bier" else 1)
                neu_f    = st.text_input("Farbe",       value=eintrag["farbe"])
                neu_desc = st.text_area("Beschreibung", value=eintrag["beschreibung"], height=70)
                if st.form_submit_button("💾 Speichern", type="primary", use_container_width=True):
                    for e in st.session_state.sammlung:
                        if e["row"] == row_key:
                            e["brauerei"]     = neu_b
                            e["getraenk"]     = neu_g
                            e["land"]         = neu_l
                            e["farbe"]        = neu_f
                            e["beschreibung"] = neu_desc
                            eintrag.update({"brauerei": neu_b, "getraenk": neu_g,
                                            "land": neu_l, "farbe": neu_f, "beschreibung": neu_desc})
                            break
                    st.session_state.edit_rows[row_key] = False
                    sheet = connect_to_sheet()
                    if sheet:
                        aktualisiere_zeile(sheet, row_key, neu_b, neu_g, neu_l, neu_desc, eintrag["bild_url"], neu_f)
                    st.toast(f"💾 {neu_b} gespeichert!")
                    st.rerun(scope="fragment")
        st.markdown("---")

    if not sammlung:
        st.info("Keine Eintraege gefunden.")
    else:
        for zeile in [sammlung[i:i+4] for i in range(0, len(sammlung), 4)]:
            cols = st.columns(4)
            for j, eintrag in enumerate(zeile):
                with cols[j]:
                    karte(eintrag)

# ══════════════════════════════════════════════════════════════════════════════
# TAB STATISTIKEN
# ══════════════════════════════════════════════════════════════════════════════
with tab_stats:
    st.title("📊 Statistiken")
    alle = get_sammlung()
    if not alle:
        st.info("Noch keine Kronkorken in der Sammlung.")
    else:
        df = pd.DataFrame(alle)
        df_stats = df[(df["brauerei"].str.lower() != "unbekannt") & (df["land"].str.lower() != "unbekannt")]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🍺 Kronkorken gesamt", len(df))
        c2.metric("🏭 Brauereien",        df_stats["brauerei"].nunique())
        c3.metric("🌍 Länder",            df_stats["land"].nunique())
        c4.metric("🍻 Davon Bier",        len(df[df["getraenk"] == "Bier"]))
        st.markdown("---")

        # Weltkarte
        st.subheader("🌍 Weltkarte meiner Sammlung")
        df_karte = df_stats.copy()
        df_karte["iso"] = df_karte["land"].map(LAND_ISO)
        df_karte_grp = df_karte.dropna(subset=["iso"]).groupby(["land", "iso"]).size().reset_index(name="Anzahl")
        if not df_karte_grp.empty:
            fig_map = px.choropleth(
                df_karte_grp, locations="iso", color="Anzahl",
                hover_name="land", hover_data={"Anzahl": True, "iso": False},
                color_continuous_scale=[[0.0,"#FFF9C4"],[0.3,"#F9A825"],[0.6,"#E65100"],[1.0,"#B71C1C"]],
                projection="natural earth",
            )
            fig_map.update_layout(
                geo=dict(showframe=False, showcoastlines=True, coastlinecolor="lightgrey",
                         showland=True, landcolor="#F5F5F5", showocean=True, oceancolor="#EBF5FB",
                         showcountries=True, countrycolor="lightgrey"),
                margin=dict(t=0,b=0,l=0,r=0),
                coloraxis_colorbar=dict(title="Kronkorken"), height=500,
            )
            st.plotly_chart(fig_map, width="stretch")
            nicht_erkannt = df_stats[~df_stats["land"].isin(LAND_ISO.keys())]["land"].unique()
            if len(nicht_erkannt) > 0:
                with st.expander(f"⚠️ {len(nicht_erkannt)} Länder nicht auf Karte"):
                    st.write(", ".join(sorted(nicht_erkannt)))
        st.markdown("---")

        col_l, col_r = st.columns(2)
        with col_l:
            st.subheader("🌍 Nach Land")
            lc = df_stats["land"].value_counts().reset_index()
            lc.columns = ["Land", "Anzahl"]
            fig = px.pie(lc, names="Land", values="Anzahl", hole=0.3,
                         color_discrete_sequence=px.colors.qualitative.Set3)
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(showlegend=False, margin=dict(t=10,b=10,l=10,r=10))
            st.plotly_chart(fig, width="stretch")
        with col_r:
            st.subheader("🏭 Top Brauereien")
            bc = df_stats["brauerei"].value_counts().head(15).reset_index()
            bc.columns = ["Brauerei", "Anzahl"]
            fig2 = px.bar(bc, x="Anzahl", y="Brauerei", orientation="h",
                          color="Anzahl", color_continuous_scale="Blues")
            fig2.update_layout(yaxis=dict(autorange="reversed"), showlegend=False,
                               margin=dict(t=10,b=10,l=10,r=10), coloraxis_showscale=False)
            st.plotly_chart(fig2, width="stretch")

        col_l2, col_r2 = st.columns(2)
        with col_l2:
            st.subheader("🎨 Nach Kronkorkenfarbe")
            fc = df[df["farbe"] != ""]["farbe"].value_counts().reset_index()
            fc.columns = ["Farbe", "Anzahl"]
            if not fc.empty:
                farb_farben = [FARB_MAP.get(f, "#CCCCCC") for f in fc["Farbe"]]
                fig3 = px.pie(fc, names="Farbe", values="Anzahl", hole=0.3,
                              color="Farbe", color_discrete_map=FARB_MAP)
                fig3.update_traces(textposition="inside", textinfo="percent+label",
                                   marker=dict(colors=farb_farben, line=dict(color="#ffffff", width=2)))
                fig3.update_layout(showlegend=False, margin=dict(t=10,b=10,l=10,r=10))
                st.plotly_chart(fig3, width="stretch")
        with col_r2:
            st.subheader("🍺 Bier vs. Kein Bier")
            gc = df["getraenk"].value_counts().reset_index()
            gc.columns = ["Typ", "Anzahl"]
            fig4 = px.pie(gc, names="Typ", values="Anzahl", hole=0.3,
                          color_discrete_map={"Bier": "#F4A300", "Kein Bier": "#4A90D9"})
            fig4.update_traces(textposition="inside", textinfo="percent+label")
            fig4.update_layout(showlegend=False, margin=dict(t=10,b=10,l=10,r=10))
            st.plotly_chart(fig4, width="stretch")

        st.markdown("---")
        st.subheader("📋 Alle Einträge")
        st.dataframe(
            df[["brauerei","getraenk","land","farbe","beschreibung"]].rename(columns={
                "brauerei":"Brauerei","getraenk":"Getränk","land":"Land",
                "farbe":"Farbe","beschreibung":"Beschreibung"
            }),
            width="stretch", hide_index=True
        )

# ══════════════════════════════════════════════════════════════════════════════
# TAB RE-SCAN
# ══════════════════════════════════════════════════════════════════════════════
with tab_rescan:
    st.title("🔄 Re-Scan nicht verifizierter Kronkorken")
    st.write("Alle Kronkorken ohne ✅ werden nochmal durch die KI geschickt — nur Brauerei und Land werden aktualisiert.")

    sammlung_rescan = get_sammlung()
    nicht_verifiziert = [e for e in sammlung_rescan if e.get("verifiziert", "") != "✅"]
    verifiziert = [e for e in sammlung_rescan if e.get("verifiziert", "") == "✅"]

    col1, col2 = st.columns(2)
    col1.metric("⬜ Nicht verifiziert", len(nicht_verifiziert))
    col2.metric("✅ Verifiziert", len(verifiziert))

    st.markdown("---")

    if nicht_verifiziert:
        st.info(f"{len(nicht_verifiziert)} Kronkorken werden neu analysiert. Das kann je nach Anzahl einige Minuten dauern.")

        if st.button("🔄 Re-Scan starten", type="primary"):
            sheet = connect_to_sheet()
            if sheet:
                fortschritt = st.progress(0)
                status_box = st.empty()
                gesamt = len(nicht_verifiziert)
                aktualisiert = 0
                fehler_count = 0

                for i, eintrag in enumerate(nicht_verifiziert):
                    status_box.write(f"Analysiere {i+1}/{gesamt}: **{eintrag['brauerei']}**")

                    if not eintrag["bild_url"] or not eintrag["bild_url"].startswith("http"):
                        st.warning(f"⚠️ Kein Bild für {eintrag['brauerei']} — übersprungen")
                        fehler_count += 1
                        fortschritt.progress((i+1)/gesamt)
                        continue

                    result, fehler = rescan_brauerei_land(eintrag["bild_url"])

                    if fehler:
                        st.error(f"❌ {eintrag['brauerei']}: {fehler}")
                        fehler_count += 1
                    else:
                        neu_b = result.get("brauerei", eintrag["brauerei"]).strip()
                        neu_l = result.get("land", eintrag["land"]).strip()

                        # Nur updaten wenn sich was geändert hat
                        if neu_b != eintrag["brauerei"] or neu_l != eintrag["land"]:
                            try:
                                sheet.update(f"A{eintrag['row']}", [[neu_b]])
                                sheet.update(f"C{eintrag['row']}", [[neu_l]])
                                st.success(f"✅ {eintrag['brauerei']} → **{neu_b}** | {eintrag['land']} → **{neu_l}**")
                                aktualisiert += 1
                            except Exception as e:
                                st.error(f"❌ Sheet-Fehler: {e}")
                                fehler_count += 1
                        else:
                            st.caption(f"— {neu_b} ({neu_l}) — keine Änderung")

                    fortschritt.progress((i+1)/gesamt)

                status_box.empty()
                invalidiere_cache()
                st.markdown("---")
                c1, c2, c3 = st.columns(3)
                c1.metric("✅ Aktualisiert", aktualisiert)
                c2.metric("— Keine Änderung", gesamt - aktualisiert - fehler_count)
                c3.metric("❌ Fehler", fehler_count)
                if aktualisiert > 0:
                    st.balloons()
    else:
        st.success("🎉 Alle Kronkorken sind bereits verifiziert!")
