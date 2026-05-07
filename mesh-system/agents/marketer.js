import { GoogleGenerativeAI } from "@google/generative-ai";

/**
 * MarketerAgent
 * Spezialisiert auf die Extraktion technischer Errungenschaften und deren Transformation 
 * in hochgradig konvertierende Marketing-Assets für Sovereign Studio V3.
 * Fokus: NoCode-Problemlösung, Early Bird Scarcity und Multi-Channel Distribution.
 */
export class MarketerAgent {
  constructor(apiKey) {
    this.genAI = new GoogleGenerativeAI(apiKey);
    this.model = this.genAI.getGenerativeModel({ model: "gemini-1.5-pro" });
    this.brandVoice = "Visionär, technisch präzise, souverän und disruptiv.";
    this.pricing = {
      anchorPrice: "6.49€",
      totalEarlyBirdCodes: 135,
      ghostMarketingPool: 66,
      offerType: "Early Bird Access"
    };
    this.coreContext = `
      Sovereign Studio V3: Autonomous AI-powered repository architect.
      Stack: Vite/React Core, Capacitor 6 Native Android, ATO-V2 Intelligence Mesh.
      Value Prop: Überwindet NoCode-Limits durch echte autonome Software-Produktion.
    `;
  }

  /**
   * Generiert Release-Ankündigungen basierend auf Build-Metriken.
   */
  async generateReleaseNotes(version, diffData, buildMetrics) {
    const prompt = `
      Handle als Lead Marketing Agent für Sovereign Studio.
      Erstelle eine Release-Ankündigung für Version ${version}.
      
      KONTEXT:
      ${this.coreContext}
      TECHNISCHE ÄNDERUNGEN: ${JSON.stringify(diffData)}
      METRIKEN: ${JSON.stringify(buildMetrics)}
      
      AUFGABE:
      1. Headline: Die Evolution des autonomen Codings.
      2. Benefit: Fokus auf die Beseitigung manueller Gradle/Vite-Hürden.
      3. Sektion "Technischer Durchbruch": Basierend auf Metriken.
      
      TONALITÄT: ${this.brandVoice}
      FORMAT: Markdown.
    `;

    const result = await this.model.generateContent(prompt);
    return result.response.text();
  }

  /**
   * Erstellt plattformspezifischen Content für Reddit, Twitter und Discord.
   * Fokus auf NoCode-Problemlösung und den 6,49€ Ankerpreis.
   */
  async generateSocialMediaCampaign(featureUpdate) {
    const scarcityInfo = `Preis: ${this.pricing.anchorPrice} | Verfügbare Early Bird Codes: ${this.pricing.totalEarlyBirdCodes} (davon ${this.pricing.ghostMarketingPool} für Erst-Launch reserviert).`;
    
    const prompt = `
      Erstelle Marketing-Inhalte für drei Kanäle basierend auf diesem Feature: ${JSON.stringify(featureUpdate)}
      
      ZENTRALE BOTSCHAFT:
      - NoCode-Tools scheitern an Komplexität? Sovereign Studio löst das durch autonome KI-Orchestrierung (ATO-V2).
      - Echte Native Android Apps (APK/AAB) direkt aus dem Prompt.
      - Unschlagbarer Preis: ${this.pricing.anchorPrice}.
      
      KANÄLE:
      1. REDDIT (r/nocode, r/reactnative): Ein "Problem-Solution" Post. Fokus auf den Schmerz von NoCode-Limits.
      2. TWITTER/X: Ein technischer Hype-Thread (5 Posts). Nutze Symbole, betone "Ghost-Pilot CI/CD".
      3. DISCORD: Community-Ankündigung. Direkt, motivierend, "Get your Code now" Call-to-Action.
      
      SCARCITY:
      Betone den ${this.pricing.offerType} mit nur ${this.pricing.totalEarlyBirdCodes} Codes insgesamt.
      
      FORMAT: Trenne die Kanäle mit "---".
    `;

    const result = await this.model.generateContent(prompt);
    return this._parseMultiChannelResponse(result.response.text());
  }

  /**
   * Erstellt Play Store Beschreibungen mit Fokus auf Capacitor 6 Performance.
   */
  async generatePlayStoreAssets(versionFeatures) {
    const prompt = `
      Erstelle Play Store "Neuigkeiten" und eine Kurzbeschreibung.
      Fokus: Native Performance durch Capacitor 6, Autonomes Patching, 0% manueller Code-Aufwand.
      Feature-Set: ${JSON.stringify(versionFeatures)}
      Maximiere technische Glaubwürdigkeit für Android-Entwickler.
    `;

    const result = await this.model.generateContent(prompt);
    return result.response.text();
  }

  /**
   * Analysiert den Repo-Status für "Autonomous Evolution" Content.
   */
  async createGhostMarketingPush(repoState) {
    const prompt = `
      Analysiere den Status: ${JSON.stringify(repoState)}
      Erstelle eine Kampagne, die zeigt, wie Sovereign Studio sich selbst verbessert hat.
      Nutze die ${this.pricing.ghostMarketingPool} reservierten Codes als "Ghost-Marketing" Initial-Zünder.
      Slogan-Vorschlag: "The engine that builds itself. For ${this.pricing.anchorPrice}."
    `;

    const result = await this.model.generateContent(prompt);
    return result.response.text();
  }

  /**
   * Hilfsmethode zur Strukturierung von Multi-Channel Content.
   */
  _parseMultiChannelResponse(text) {
    const segments = text.split("---");
    return {
      reddit: segments[0] ? segments[0].trim() : "",
      twitter: segments[1] ? segments[1].trim() : "",
      discord: segments[2] ? segments[2].trim() : "",
      raw: text
    };
  }
}

export default MarketerAgent;