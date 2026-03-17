# BiblioForge - Data Cleaning Script

## Descrizione

Script Python per la pulizia e trasformazione del database di libri grezzo (XLSX) in formato strutturato (CSV) per BiblioForge.

## Requisiti

- Python 3.7+
- pandas
- openpyxl (per lettura Excel)

Installare le dipendenze:
```bash
pip install pandas openpyxl
```

## Uso

Eseguire lo script dalla cartella root del progetto:

```bash
python clean_books.py
```

## Trasformazioni Applicate

### 1. Rinominazione Colonne
- La colonna `Q.t` (con caratteri speciali) viene rinominata in `Quantità`

### 2. Split Titolo-Autore
- La colonna `TITOLO - AUTORE` viene separata in due colonne distinte:
  - `Titolo`: contiene il titolo del libro
  - `Autore`: contiene il nome dell'autore
- Utilizza `split(' - ', n=1)` per gestire separatori multipli
- Se non presente, il valore va interamente nel Titolo

### 3. Pulizia Spazi
- Tutti i valori di testo vengono processati con `.strip()`
- Rimuove spazi superflui all'inizio e alla fine

### 4. Formattazione Prezzo
- La colonna `Prezzo` viene formattata come stringa con formato `EUR x.xx`
- Esempio: `6.9` → `EUR 6.90`

### 5. Conversione Quantità
- La colonna `Quantità` viene convertita a intero
- Valori mancanti vengono sostituiti con 0

### 6. Riordino Colonne
Ordine finale nel file CSV:
1. Codice EAN
2. Cod. Ed. Int.
3. Titolo
4. Autore
5. EDITORE
6. Quantità
7. Prezzo

## Input/Output

**Input**: `biblioforge/data/raw/Stampa_Libri_Interni_RAW.xlsx`
**Output**: `biblioforge/data/cleaned/books_cleaned.csv`

## Gestione Errori

Lo script include:
- Verifiche di esistenza dei file
- Gestione di valori mancanti (NaN)
- Gestione di separatori multipli nel split
- Creazione automatica della cartella output se non esiste
- Try-catch globale con traceback completo

## Statistiche Elaborazione

Il file di input contiene **2526 record** che vengono elaborati e salvati nel file CSV pulito.

## Output di Esempio

```
[1/8] Lettura del file Excel grezzo...
    > Caricati 2526 record

[2/8] Rinominazione colonne...
    > Colonna 'Q.t' rinominata a 'Quantità'

[3/8] Separazione TITOLO - AUTORE...
    > Colonna 'TITOLO - AUTORE' separata in 'Titolo' e 'Autore'

[4/8] Rimozione spazi superflui (strip)...
    > Spazi rimossi da 5 colonne di testo

[5/8] Formattazione colonna Prezzo...
    > Prezzo formattato con simbolo Euro

[6/8] Conversione Quantità a intero...
    > Quantità convertita a intero

[7/8] Riordino colonne...
    > Colonne riordinate

[8/8] Creazione cartella output...
    > Cartella già esistente: C:\...\biblioforge\data\cleaned

[9/9] Salvataggio file CSV...
    > File salvato: C:\...\biblioforge\data\cleaned\books_cleaned.csv

PULIZIA COMPLETATA CON SUCCESSO!
```

## Campione dei Dati Puliti

| Codice EAN | Cod. Ed. Int. | Titolo | Autore | EDITORE | Quantità | Prezzo |
|---|---|---|---|---|---|---|
| 9791280495488 | NaN | (SENZA) RESIDENZA | GARGIULO ENRICO | V-ERIS | 1 | EUR 6.90 |
| 9788822901637 | NaN | MELENCOLIA I DI DÜRER... | PANOFSKY ERWIN; SAXL... | v-quodlibet | 1 | EUR 24.00 |
| 9788804765332 | NaN | RECHERCHE DI PROUST... | RABONI GIOVANNI | V-MONDADORI | 1 | EUR 13.00 |

## Encoding

Il file CSV viene salvato con encoding **UTF-8 BOM** (`utf-8-sig`) per garantire compatibilità con programmi come Excel mantenendo i caratteri accentati italiani.

---

**Progetto**: BiblioForge  
**Data**: 2026  
**Versione**: 1.0

