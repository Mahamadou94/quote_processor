# OCR Combined LLM Service

Service FastAPI combinant OCR et LLM pour l'extraction automatique de données structurées à partir de devis BTP au format PDF.

## 📋 Description

Ce microservice utilise une approche hybride combinant :
- **Extraction de texte native** (pdftotext) pour les PDF textuels
- **OCR optique** (PaddleOCR) pour les documents scannés
- **Intelligence artificielle** (OpenAI GPT-4o) pour structurer les données extraites

Le service est spécifiquement conçu pour extraire des informations commerciales à partir de devis du secteur BTP (Bâtiment et Travaux Publics) en français.

## ✨ Fonctionnalités

- ✅ Extraction intelligente avec fallback automatique (texte natif → OCR)
- ✅ Traitement adaptatif selon le type de document
- ✅ Déduplication automatique des lignes extraites
- ✅ Résolution adaptative pour une meilleure précision OCR
- ✅ Métriques de performance détaillées (temps OCR, LLM, total)
- ✅ API REST avec endpoints de santé
- ✅ Déploiement Docker avec health checks

## 🎯 Données Extraites

Le service extrait 8 champs principaux :

```json
{
  "ref_imh": "Numéro de référence IMH",
  "customer_name": {"value": "Nom du client"},
  "customer_address": {"value": "Adresse du client"},
  "construction_site_address": {"value": "Adresse du chantier"},
  "supplier_name": {"value": "Nom de l'entreprise fournisseur"},
  "supplier_address": {"value": "Adresse du fournisseur"},
  "supplier_name_shareholder": {"value": "Nom de l'actionnaire si mentionné"},
  "supplier_address_shareholder": {"value": "Adresse de l'actionnaire si mentionné"},
  "temps_ocr_secondes": 2.45,
  "temps_llm_secondes": 3.12,
  "temps_traitement_secondes": 5.57
}
```

## 🚀 Démarrage Rapide

### Prérequis

- Docker et Docker Compose installés
- Clé API OpenAI

### Installation

1. **Cloner le projet**
```bash
git clone <repository-url>
cd ocr_combined_llm_service
```

2. **Configurer les variables d'environnement**
```bash
cp .env.exemple .env
```

3. **Éditer le fichier `.env`**
```env
PYTHONUNBUFFERED=1
ORGA_OPENAI_API_KEY=your_openai_api_key_here
```

4. **Lancer le service**
```bash
docker-compose up --build
```

Le service sera accessible sur `http://localhost:8000`

## 📡 API Endpoints

### `GET /`
Point d'entrée racine, retourne le statut du service.

**Réponse :**
```json
{
  "message": "OCR + LLM Devis BTP - Service opérationnel",
  "version": "1.0-light"
}
```

### `GET /health`
Endpoint de santé pour monitoring.

**Réponse :**
```json
{
  "status": "ok"
}
```

### `POST /process`
Traitement d'un fichier PDF.

**Requête :**
- Content-Type: `multipart/form-data`
- Paramètre: `file` (fichier PDF)

**Exemple avec curl :**
```bash
curl -X POST http://localhost:8000/process \
  -F "file=@/chemin/vers/devis.pdf"
```

**Réponse :**
```json
{
  "ref_imh": "IMH123456",
  "customer_name": {"value": "Entreprise Client SARL"},
  "customer_address": {"value": "123 Rue de Paris, 75001 Paris"},
  "construction_site_address": {"value": "45 Avenue du Chantier, 75002 Paris"},
  "supplier_name": {"value": "Fournisseur BTP SAS"},
  "supplier_address": {"value": "67 Boulevard du Commerce, 75003 Paris"},
  "supplier_name_shareholder": {"value": null},
  "supplier_address_shareholder": {"value": null},
  "temps_ocr_secondes": 2.45,
  "temps_llm_secondes": 3.12,
  "temps_traitement_secondes": 5.57
}
```

## 🏗️ Architecture

### Stack Technique

- **Framework Web :** FastAPI 0.104.1
- **Serveur ASGI :** Uvicorn 0.24.0
- **OCR :** PaddleOCR 2.7.0.3 + PaddlePaddle 2.6.2
- **PDF :** PyMuPDF (fitz) 1.20.0 + poppler-utils
- **LLM :** OpenAI API (GPT-4o)
- **Image :** Pillow 10.1.0
- **Validation :** Pydantic 2.5.0

### Workflow de Traitement

```
PDF Upload
    ↓
[Extraction Native avec pdftotext]
    ↓
Texte > 30 lignes ? → OUI → OCR page 1 uniquement
    ↓
    NON
    ↓
OCR de toutes les pages (document scanné)
    ↓
[Déduplication des lignes]
    ↓
[Traitement LLM avec GPT-4o]
    ↓
JSON Structuré
```

### Optimisations

- **Sélection intelligente de pages :** OCR adaptatif selon le contenu
- **Résolution dynamique :** 2.5x pour en-têtes, 2x pour corps de texte
- **Thread-safe :** Verrouillage pour l'accès concurrent à l'OCR
- **Async/await :** Traitement non-bloquant

## 🐳 Déploiement Docker

### Structure Docker

- **Base image :** Python 3.10-slim
- **Utilisateur non-root :** `appuser` (sécurité)
- **Port exposé :** 8000
- **Health check :** Toutes les 30s avec 3 tentatives
- **Politique de restart :** unless-stopped

### Commandes Docker

**Build manuel :**
```bash
docker build -t ocr-llm-service .
```

**Run manuel :**
```bash
docker run -p 8000:8000 \
  -e ORGA_OPENAI_API_KEY=your_key \
  ocr-llm-service
```

**Avec Docker Compose (recommandé) :**
```bash
# Démarrage
docker-compose up -d

# Logs
docker-compose logs -f

# Arrêt
docker-compose down
```

## 📊 Métriques de Performance

Le service retourne des métriques temporelles pour chaque requête :

- `temps_ocr_secondes` : Temps d'extraction OCR
- `temps_llm_secondes` : Temps de traitement LLM
- `temps_traitement_secondes` : Temps total

**Facteurs influençant les performances :**
- Taille et nombre de pages du PDF
- Qualité de scan (résolution, contraste)
- Présence de texte natif vs. images scannées
- Charge du service OpenAI

## 🔒 Sécurité

- ✅ Exécution en utilisateur non-root
- ✅ Variables d'environnement pour secrets
- ✅ Validation des entrées avec Pydantic
- ✅ Isolation réseau Docker
- ⚠️ **Important :** Ne jamais committer le fichier `.env` avec des clés API

## 🛠️ Développement

### Installation locale (sans Docker)

```bash
# Créer un environnement virtuel
python3.10 -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows

# Installer les dépendances
pip install -r requirements.txt

# Installer poppler-utils (pour pdftotext)
# Ubuntu/Debian
sudo apt-get install poppler-utils

# macOS
brew install poppler

# Lancer le service
uvicorn fastapi_ocr_llm_light_app:app --reload --host 0.0.0.0 --port 8000
```

### Structure du Projet

```
ocr_combined_llm_service/
├── fastapi_ocr_llm_light_app.py    # Application principale (365 lignes)
├── Dockerfile                       # Configuration Docker
├── docker-compose.yml              # Orchestration
├── requirements.txt                # Dépendances Python
├── .env.exemple                    # Template de configuration
├── .env                            # Configuration locale (git-ignored)
├── .gitignore                      # Exclusions Git
└── README.md                       # Documentation
```

## 📝 Fichier de Configuration

Le fichier `.env` doit contenir :

```env
# Désactive le buffering Python (logs en temps réel)
PYTHONUNBUFFERED=1

# Clé API OpenAI (OBLIGATOIRE)
ORGA_OPENAI_API_KEY=sk-proj-...
```

## 🐛 Dépannage

### Le service ne démarre pas

```bash
# Vérifier les logs
docker-compose logs -f ocr_llm_service

# Vérifier la clé API
grep ORGA_OPENAI_API_KEY .env
```

### Erreur "Empty file or corrupted PDF"

- Vérifier que le PDF n'est pas corrompu
- Tester avec un autre PDF
- Vérifier les permissions du fichier

### Performances lentes

- Les documents scannés sont plus lents (OCR complet)
- Vérifier la charge de l'API OpenAI
- Considérer l'optimisation de résolution pour de gros documents


