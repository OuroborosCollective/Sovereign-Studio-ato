#!/bin/bash
# Setup script for Sovereign LLM Proxy
# Führt wrangler secret puts für alle benötigten Secrets aus

set -e

echo "🔐 Sovereign LLM Proxy - Secret Setup"
echo "======================================"
echo ""

# Farben für Output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if wrangler is installed
if ! command -v wrangler &> /dev/null; then
    echo -e "${RED}❌ Wrangler CLI nicht gefunden!${NC}"
    echo "Installiere wrangler: npm install -g wrangler"
    exit 1
fi

echo -e "${GREEN}✓ Wrangler gefunden${NC}"
echo ""

# Check if logged in
echo "Prüfe Cloudflare Authentifizierung..."
if wrangler whoami &> /dev/null; then
    echo -e "${GREEN}✓ Bereits angemeldet${NC}"
else
    echo -e "${YELLOW}⚠ Nicht angemeldet - bitte 'wrangler login' ausführen${NC}"
    echo "Führe 'wrangler login' aus und starte dieses Script erneut."
    exit 1
fi
echo ""

# Function to set secret with input
set_secret() {
    local name=$1
    local description=$2
    local required=$3
    local default=$4
    
    echo "----------------------------------------"
    echo -e "${YELLOW}📝 $name${NC}"
    echo "$description"
    
    if [ -n "$default" ]; then
        read -p "Wert eingeben (Enter für Standard: $default): " value
        value=${value:-$default}
    else
        read -p "Wert eingeben: " value
    fi
    
    if [ -z "$value" ]; then
        if [ "$required" = "true" ]; then
            echo -e "${RED}❌ Pflichtfeld - Cannot be empty${NC}"
            exit 1
        else
            echo -e "${YELLOW}⚠ Übersprungen (optional)${NC}"
            return 0
        fi
    fi
    
    echo "$value" | wrangler secret put "$name" --name sovereign-llm-proxy
    echo -e "${GREEN}✓ $name gesetzt${NC}"
}

# Set required secrets
echo "Bitte konfiguriere die Secrets:"
echo ""

set_secret "CF_AI_TOKEN" "Cloudflare AI API Token (cfut_...)" "true" ""
set_secret "CF_ACCOUNT_ID" "Cloudflare Account ID (32-stellige ID)" "true" ""

echo ""
echo "----------------------------------------"
echo "Optionale Secrets:"
echo ""

read -p "Erlaubte Modelle (kommasepariert, Enter für alle): " models
if [ -n "$models" ]; then
    echo "$models" | wrangler secret put "ALLOWED_MODELS" --name sovereign-llm-proxy
    echo -e "${GREEN}✓ ALLOWED_MODELS gesetzt${NC}"
else
    echo -e "${YELLOW}⚠ ALLOWED_MODELS übersprungen (alle Modelle erlaubt)${NC}"
fi

read -p "Default Model (Enter für @cf/meta/llama-3-8b-instruct): " default_model
if [ -n "$default_model" ]; then
    echo "$default_model" | wrangler secret put "DEFAULT_MODEL" --name sovereign-llm-proxy
    echo -e "${GREEN}✓ DEFAULT_MODEL gesetzt${NC}"
else
    echo -e "${YELLOW}⚠ DEFAULT_MODEL übersprungen${NC}"
fi

echo ""
echo "========================================"
echo -e "${GREEN}✅ Secret Setup abgeschlossen!${NC}"
echo ""
echo "Nächste Schritte:"
echo "  1. npm install && npm run deploy  - Worker deployen"
echo "  2. npm run tail                  - Logs überwachen"
