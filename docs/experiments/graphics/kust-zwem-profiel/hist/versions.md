# Ontwerp-Evolutie Kustzwem-Profiel (Graphics Changelog)

Dit document beschrijft de evolutie van het **Kustzwem-Trajectprofiel** in `docs/experiments/graphics/kust-zwem-profiel/`.

---

### Versieoverzicht

| Versie | Bronbestanden (in `./hist/`) | Belangrijkste Kenmerken & Wijzigingen |
| :--- | :--- | :--- |
| **v0** | `ontwerp-kustzwem-profiel-v0.png` | **Oorspronkelijke handschets door Marc Portier**: Concept van een tijd-ruimte diagram met vaste 750m afstandspunten en verticaal verschoven getijdenvisgraten volgens de doorkomsttijd van de zwemmer. Drie doorkomsttijd-scenario's (blauw, groen, oranje). |
| **v1** | `generate_v1.py`<br>`ontwerp-kustzwem-profiel-v1.svg`<br>`ontwerp-kustzwem-profiel-v1.png` | **Eerste Digitale Vector Prototype**: <br>• 5 checkpoints op 750m intervallen (0.0k tot 3.0k: Bredene Post 4 ➔ De Haan).<br>• Verticale visgraten per checkpoint met actuele stromingsvectoren (vloed naar rechts, eb naar links, kentering groen).<br>• Horizontale groene zichtlijn voor de referentiezwemmer (1.0 m/s cruise).<br>• Schuine doorkomsttrajecten voor snelle zwemmers (blauw, stijgend = vroeger) en recreatieve zwemmers (oranje, dalend = later).<br>• Timing-overzichtskaartjes onderaan per checkpoint.<br>• 100% vector SVG en hoge resolutie PNG preview. |
| **v2** | *(Geparkeerd in Backlog)* | **Isotachen-Mesh, Isochronen & Schaalbaarheid (Ontwerpvisie)**: <br>• **Ontkoppelde Afstandsas**: Pure afstandsmarkers (`0k0`, `0k75`, `1k5`, `2k25`, ... 90° gekanteld), losgekoppeld van arbitraire post-nummers.<br>• **Bovenbalk Kust-Landmarks**: Bovenliggende geostrip met reële merkpunten (havengeulen en staketsels van Nieuwpoort, Oostende, Blankenberge, Zeebrugge).<br>• **Isotachen (Snelheidscontouren)**: Vloeiende spectrale mesh (in stappen van 0.1 m/s van 0.5 tot 1.5 m/s) rondom een gepersonaliseerde referentie-centersnelheid ($v_0 \pm 0.5\text{ m/s}$).<br>• **Isochronen (Tijdcontouren)**: Dunne 15-minuten tijdlijnen (`HH:MM`) door de verschoven visgraten, die direct doorkomsttijd en tijd-ruimtetransformatie visualiseren (onderste tabel overbodig).<br>• **Heen-en-Terug ("Out-and-Back")**: Spiegeling/kanteling van de terugweg rechts in lijn.<br>• **Schaalbaarheid**: Flexibele afstandsas voor lange tochten (16k, 20k, 67k *Ommeweg vzw*). |

---

### Actieve Canonieke Bestanden & `./latest` Symlinks
De actieve versie (momenteel gelijk aan **v1**) staat klaar in:
- Directory: [`../latest/`](../latest/)
  - `ontwerp-kustzwem-profiel.svg` -> `../hist/ontwerp-kustzwem-profiel-v1.svg`
  - `ontwerp-kustzwem-profiel-preview.png` -> `../hist/ontwerp-kustzwem-profiel-v1.png`
