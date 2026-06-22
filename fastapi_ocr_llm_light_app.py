# -*- coding: utf-8 -*-
"""
Service FastAPI - OCR + LLM pour extraction légère (Version simplifiée)
Extraction brute : pdftotext (texte natif) ou PaddleOCR (scan)
"""

import os
import json
import tempfile
import time
import subprocess
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from paddleocr import PaddleOCR
from PIL import Image
from dotenv import load_dotenv
from openai import OpenAI
from openai import AsyncOpenAI  
import asyncio
import threading
import fitz
import numpy as np

load_dotenv()

OPENAI_KEY = os.getenv("ORGA_OPENAI_API_KEY", "")
client_llm = OpenAI(api_key=OPENAI_KEY)

app = FastAPI(
    title="OCR + LLM Devis BTP - Extraction Légère",
    description="Upload un PDF → Extraction texte → LLM → JSON structuré",
    version="1.0.0-light"
)

# ===============================
# OCR INSTANCE GLOBALE
# ===============================
_ocr_instance = None
_ocr_lock = threading.Lock()

def get_ocr_instance():
    """Obtenir l'instance OCR globale."""
    global _ocr_instance
    if _ocr_instance is None:
        with _ocr_lock:
            if _ocr_instance is None:
                _ocr_instance = PaddleOCR(use_angle_cls=True, lang="latin", use_gpu=False)
    return _ocr_instance

# ===============================
# PROMPT LLM 
# ===============================
PROMPT_HEAD = """
Tu es un expert en lecture de devis BTP. Analyse les lignes OCR et extrais :

1. ref_imh : Format accepté "XXXXXXX-REXPX /X" ou "XXXXXXX – XXXXXX" ou "Vos réf. :   XXXXXXX" ou "Réf compagnie :  XXXXXXXX" ou "N° PRESTATAIRE : XXXXXX" ou ""XXXXXXHXX-REN_EXPX" ou "null"
2. customer_name : Nom du client pas autre chose
3. customer_address : Adresse complète du client pas autre chose
4. construction_site_address : Cherche "Chantier :" ou "Chantier/Bénéficiaire :" ou "adresse chantier :" ou "addresse travaux :" ou "lieu du chantier :" ou "lieu des travaux :" → adresse complète (si différente du client sinon prendre l'adresse client à la place)
5. supplier_address : Adresse complète du fournisseur pas autre chose 
6. supplier_address_shareholder : Adresse complète sociétaire si mentionné dans le devis sinon prendre l'adresse de la société
7. supplier_name : Nom complet de la société du fournisseur pas autre chose
8. supplier_name_shareholder : Nom sociétaire complet si mentionné dans le devis sinon prendre le nom de la société pas autre chose.
Format JSON :
{
    "ref_imh": {"value": "XXXXXXX-REXPX /X" ou "XXXXXXX – XXXXXX" ou "Vos réf. :   XXXXXXX" ou "Réf compagnie :  XXXXXXXX" ou "XXXXXXHXX-REN_EXPX" ou "null"},
    "customer_address": {
            "value": "Adresse complète du client" ou null      
        },
    "customer_name": {
        "value": "Nom complet du client" ou null
        },
    "construction_site_address": {
           
            "value": "Adresse complète du chantier" ou null      
        },
    "supplier_name": {"value": "Nom complet de la société" ou null},
    "supplier_address": {
          
            "value": "Adresse complète du fournisseur" ou null      
        },
    "supplier_name_shareholder": {"value": "Nom complet sociétaire" ou null},

    "supplier_address_shareholder": {
        
        "value": "Adresse complète" ou null
    }
}

RÈGLES :
- Attention à prioriser le format "XXXXXXHXX-REN_EXPX" ou "XXXXXXX-REXPX /X" si présent dans le devis sinon les autres formats.
- Toujours prendre "Vos réf. :   XXXXXXX" et pas "Nos réf :   XXXXXXX" 
- Cherche les en-têtes ("Client :", "Chantier :", "Réf imh :", "Prestataire :","Livraison/Chantier")
- Corrige les erreurs OCR courantes (L/l, majuscules)
- Si aucune information chantier n'est trouvée alors prendre l'adresse client à la place et prendre l'adresse client comme adresse chantier.
- N'invente rien : si absent → null
- Attention à faire la distinction entre adresse chantier, adresse société et adresse sociétaire et adresse client
- Si le nom est fragmenté sur plusieurs lignes consécutives (lignes qui se suivent), fusionner TOUTES les parties pour reconstituer le nom complet par exemple Help Confort Bordeaux 1
SAS HABITAT SEREQUAL devient "Help Confort Bordeaux 1 SAS HABITAT SEREQUAL"

Lignes OCR :
-----
"""

PROMPT_TAIL = """
-----
Rappel : Extraire ref_imh, customer_address, customer_name, construction_site_address, supplier_address, supplier_name, supplier_name_shareholder, supplier_address_shareholder. JSON strict.
"""

# ===============================
# EXTRACTION SIMPLE
# ===============================

def extract_text_simple(pdf_bytes: bytes) -> str:
    """Extraction optimisée : pdftotext + OCR intelligent (seulement si nécessaire)."""
    tmp_path = None
    try:
        # Sauvegarder le PDF
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        tmp.write(pdf_bytes)
        tmp_path = tmp.name
        tmp.close()
        
        # Étape 1 : Extraction texte natif (si disponible)
        pdftotext_lines = []
        try:
            result = subprocess.run(
                ["pdftotext", "-layout", tmp_path, "-"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False
            )
            if result.returncode == 0 and result.stdout.strip():
                pdftotext_lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
        except:
            pass
        
        # Dictionnaire pour dédoublonnage (normalisé)
        seen_lines = set()
        all_lines = []
        
        def normalize_line(line: str) -> str:
            """Normalise une ligne pour la comparaison (sans espaces, lowercase)."""
            return line.lower().replace(" ", "").replace("\t", "")
        
        # Ajouter les lignes pdftotext d'abord
        for line in pdftotext_lines:
            normalized = normalize_line(line)
            if normalized and normalized not in seen_lines:
                all_lines.append(line)
                seen_lines.add(normalized)
        
        # Étape 2 : OCR intelligent - seulement si nécessaire
        ocr = get_ocr_instance()
        doc = fitz.open(tmp_path)
        num_pages = len(doc)
        
        # Stratégie d'optimisation :
        # - Si pdftotext a trouvé beaucoup de texte (>30 lignes), faire OCR seulement sur la première page (en-tête)
        # - Sinon, faire OCR sur toutes les pages avec résolution réduite
        
        if len(pdftotext_lines) > 30:
            # Beaucoup de texte natif → OCR seulement première page (en-tête)
            pages_to_ocr = [0]  # Seulement la première page
            print(f"ℹ️  pdftotext a trouvé {len(pdftotext_lines)} lignes → OCR seulement sur la première page (en-tête)")
        else:
            # Peu de texte natif → OCR sur toutes les pages (document scanné)
            pages_to_ocr = range(num_pages)
            print(f"ℹ️  pdftotext a trouvé {len(pdftotext_lines)} lignes → OCR sur toutes les pages ({num_pages} pages)")
        
        for page_num in pages_to_ocr:
            page = doc[page_num]
            with _ocr_lock:
                # Résolution adaptative :
                # - Première page : Matrix(2.5, 2.5) pour capturer l'en-tête (bon compromis vitesse/qualité)
                # - Autres pages : Matrix(2, 2) pour vitesse
                if page_num == 0:
                    pix = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5))  # Résolution moyenne pour en-tête
                else:
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # Résolution réduite pour vitesse
                
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                np_img = np.array(img)
                
                result = ocr.ocr(np_img)
                
                if result and result[0]:
                    for blk in result[0]:
                        if len(blk) >= 2 and blk[1]:
                            txt = blk[1][0].strip()
                            if txt:
                                # Dédoublonnage intelligent
                                normalized = normalize_line(txt)
                                if normalized and normalized not in seen_lines:
                                    all_lines.append(txt)
                                    seen_lines.add(normalized)
        
        doc.close()
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        
        return "\n".join(all_lines)
        
    except Exception as e:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except:
                pass
        raise e

# ===============================
# LLM STRUCTURATION
# ===============================
async def structurer_llm_async(ocr_text: str) -> dict:
    """Appelle le LLM pour structurer."""
    # Numéroter les lignes
    lines = [l.strip() for l in ocr_text.splitlines() if l.strip()]
    numbered_text = "\n".join([f"{i+1:04d} | {l}" for i, l in enumerate(lines)])
    
    prompt = PROMPT_HEAD + numbered_text + PROMPT_TAIL
    
    loop = asyncio.get_event_loop()
    
    def call_llm():
        try:
            resp = client_llm.chat.completions.create(
                model="gpt-4o",
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=1500,
                messages=[
                    {
                        "role": "system",
                        "content": "Tu es un expert des devis BTP. Extraire ref_imh, customer_address, customer_name, construction_site_address, supplier_address, supplier_name, supplier_name_shareholder, supplier_address_shareholder. Réponds UNIQUEMENT en JSON strict."
                    },
                    {"role": "user", "content": prompt}
                ]
            )
            return json.loads(resp.choices[0].message.content)
        except Exception as e:
            raise Exception(f"Erreur LLM: {str(e)}")
    
    result = await loop.run_in_executor(None, call_llm)
    
    # Normalisation simple
    if "ref_imh" not in result:
        result["ref_imh"] = None
    
    if "customer_name" not in result:
        result["customer_name"] = {"value": None}
    else:
        if "value" not in result["customer_name"]:
            result["customer_name"]["value"] = None
    
    if "construction_site_address" not in result:
        result["construction_site_address"] = {"value": None}
    else:
        if "value" not in result["construction_site_address"]:
            result["construction_site_address"]["value"] = None
    
    if "supplier_address" not in result:
        result["supplier_address"] = {"value": None}
    else:
        if "value" not in result["supplier_address"]:
            result["supplier_address"]["value"] = None
    
    return result

# ===============================
# ENDPOINTS FASTAPI
# ===============================

@app.post("/process", tags=["OCR"])
async def process_pdf(file: UploadFile = File(...)):
    """Upload un PDF → JSON structuré."""
    start_time = time.time()
    ocr_time = 0
    llm_time = 0
    
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Le fichier doit être un PDF.")
    
    try:
        pdf_bytes = await file.read()
        if not pdf_bytes:
            raise HTTPException(status_code=400, detail="Le fichier PDF est vide.")
        
        # Extraction texte (OCR)
        ocr_start = time.time()
        loop = asyncio.get_event_loop()
        ocr_text = await loop.run_in_executor(None, extract_text_simple, pdf_bytes)
        ocr_time = round(time.time() - ocr_start, 2)
        
        print(f"\n⏱️  Temps OCR: {ocr_time} secondes")
        
        # Print du contenu OCR
        print("\n" + "=" * 80)
        print(f"CONTENU OCR EXTRAIT (fichier: {file.filename}):")
        print("=" * 80)
        print(ocr_text)
        print("=" * 80 + "\n")
        
        if not ocr_text or not ocr_text.strip():
            total_time = round(time.time() - start_time, 2)
            return JSONResponse(
                status_code=422,
                content={
                    "erreur": "Aucun texte extrait du PDF",
                    "ref_imh": None,
                    "infos_client": {"nom_client": None, "adresse_client": None},
                    "infos_chantier": {"adresse_chantier": None},
                    "infos_fournisseur": {"nom_fournisseur": None, "adresse_fournisseur": None},
                    "temps_ocr_secondes": ocr_time,
                    "temps_llm_secondes": 0,
                    "temps_traitement_secondes": total_time
                }
            )
        
        # LLM structuration
        llm_start = time.time()
        result = await structurer_llm_async(ocr_text)
        llm_time = round(time.time() - llm_start, 2)
        
        print(f"⏱️  Temps LLM: {llm_time} secondes")
        total_time = round(time.time() - start_time, 2)
        print(f"⏱️  Temps total: {total_time} secondes\n")
        
        # Ajouter les temps dans la réponse
        result["temps_ocr_secondes"] = ocr_time
        result["temps_llm_secondes"] = llm_time
        result["temps_traitement_secondes"] = total_time
        
        return JSONResponse(content=result)
        
    except HTTPException:
        raise
    except Exception as e:
        total_time = round(time.time() - start_time, 2)
        return JSONResponse(
            status_code=500,
            content={
                "erreur": f"Erreur: {str(e)}",
                "ref_imh": None,
                "infos_client": {"nom_client": None, "adresse_client": None},
                "infos_chantier": {"adresse_chantier": None},
                "infos_fournisseur": {"nom_fournisseur": None, "adresse_fournisseur": None},
                "temps_ocr_secondes": ocr_time,
                "temps_llm_secondes": llm_time,
                "temps_traitement_secondes": total_time
            }
        )

@app.get("/", tags=["Root"])
def root():
    return {"status": "OK", "endpoint": "POST /process", "version": "1.0.0-light"}

@app.get("/health", tags=["Health"])
def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
