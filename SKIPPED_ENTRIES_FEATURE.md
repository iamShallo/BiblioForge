# Feature: Track Skipped Entries During Excel Import

## Overview
Quando esegui un "Import from Excel", il sistema ora traccia tutte le righe che vengono scattate (skipped) perché non possono essere risolte con certezza. Puoi visualizzare l'elenco completo delle righe scattate direttamente nella dashboard e scaricare un rapporto JSON dettagliato.

## Cosa è stato implementato

### 1. **Tracciamento dettagliato degli skipped**
- Il controller ora memorizza i dettagli di ogni riga scattata, inclusi:
  - `index`: Indice della riga nel batch di elaborazione
  - `title`: Titolo del libro
  - `author`: Autore del libro
  - `ean`: Codice EAN (se disponibile)
  - `publisher`: Editore (se disponibile)
  - `reason`: Motivo dello skip ("Book could not be resolved confidently" o eccezione durante l'arricchimento)

### 2. **Salvataggio su file JSON**
- Un rapporto JSON viene creato automaticamente in `artifacts/reports/` con:
  - Nome file: `import_skipped_YYYYMMDD_HHMMSS.json`
  - Timestamp dell'import
  - Conteggio totale degli skip
  - Lista completa degli skipped entries

### 3. **Interfaccia utente nella Dashboard**
Dopo un import da Excel, se ci sono righe scattate:
- Viene mostrato un avviso: "Skipped {count} rows because the book could not be resolved confidently."
- Un'espandibile sezione mostra l'elenco completo dei libri scattati con:
  - Numero progressivo
  - Titolo e autore
  - EAN (se disponibile)
  - Motivo dello skip (primi 40 caratteri)
- Un pulsante di download per scaricare il rapporto JSON completo

## Modifiche ai file

### `biblioforge/controllers/pipeline_controller.py`
- **Import aggiunti**: `json`, `datetime`
- **Attributi aggiunti** in `__init__`:
  - `last_import_skipped_details: List[dict]` - Memorizza dettagli degli skipped
  - `last_import_skipped_report_path: str` - Percorso del rapporto JSON
- **Nuovi metodi**:
  - `_save_skipped_report(skipped_entries)` - Salva il rapporto in JSON
  - `get_last_skipped_report_path()` - Recupera il percorso dell'ultimo rapporto
- **Modifiche a** `ingest_books_from_excel()`:
  - Inizializza le liste di tracking
  - Modifica la funzione `_process_entries` per tracciare gli skipped
  - Chiama `_save_skipped_report()` se ci sono righe scattate

### `biblioforge/views/dashboard.py`
- **Sezione aggiornata** `render_excel_ingestion_box()`:
  - Mostra un avviso con il conteggio dei skipped
  - Espande un'espandibile sezione con l'elenco dei libri scattati
  - Fornisce un pulsante di download per il rapporto JSON

## Utilizzo

1. **Vai alla dashboard**: `streamlit run biblioforge/views/dashboard.py`
2. **Esegui un import da Excel**: Clicca "Load into review queue"
3. **Visualizza i risultati**:
   - Se il rapporto ha righe scattate, vedrai un avviso
   - Clicca su "📋 View skipped entries" per espandere l'elenco
   - Clicca su "📥 Download Skipped Report (JSON)" per scaricare il file completo

## File generato

Il rapporto JSON ha questa struttura:

```json
{
  "timestamp": "2024-03-20T14:30:45.123456",
  "total_skipped": 396,
  "skipped_entries": [
    {
      "index": 0,
      "title": "Il Nome della Rosa",
      "author": "Umberto Eco",
      "ean": null,
      "publisher": "Bompiani",
      "reason": "Book could not be resolved confidently"
    },
    ...
  ]
}
```

## Benefici

✅ **Visibilità completa**: Vedi esattamente quali libri non sono stati importati e perché
✅ **Riproducibilità**: Il rapporto JSON registra ogni dettaglio per successive analisi
✅ **UI intuitiva**: Interfaccia Streamlit integrata senza configurazioni aggiuntive
✅ **Storico**: Ogni import genera un rapporto separato timestampato

## Troubleshooting

- **Il rapporto non si scarica**: Assicurati che la cartella `artifacts/reports/` sia writable
- **Vedi "Unknown reason"**: Potrebbe esserci stata un'eccezione; controlla i log dell'applicazione

