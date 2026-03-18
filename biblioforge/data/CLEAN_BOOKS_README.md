# BiblioForge - Data Cleaning Script

## Description

Python script to clean and transform the raw book database (XLSX) into a structured XLSX format for BiblioForge.

## Requirements

- Python 3.7+
- pandas
- openpyxl (for Excel read/write)

Install dependencies:

```bash
pip install pandas openpyxl
```

## Usage

Run the script from the project root folder:

```bash
python clean_books.py
```

## Applied Transformations

### 1. Column Rename

- The `Q.t` column (possibly with special characters) is renamed to `Quantità`.

### 2. Title-Author Split

- The `TITOLO - AUTORE` column is split into two columns:
- `Titolo`: book title
- `Autore`: author name
- Uses `split(' - ', n=1)` to handle multiple separators.
- If the separator is not found, the full value is kept in `Titolo`.

### 3. Whitespace Cleanup

- All text values are processed with `.strip()`.
- Leading and trailing whitespace is removed.

### 4. Price Formatting

- The `Prezzo` column is formatted as `EUR x.xx`.
- Example: `6.9` -> `EUR 6.90`

### 5. Quantity Conversion

- The `Quantità` column is converted to integer.
- Missing values are replaced with 0.

### 6. Column Reordering

Final order in the output file:

1. Codice EAN
2. Cod. Ed. Int.
3. Titolo
4. Autore
5. EDITORE
6. Quantità
7. Prezzo

## Input/Output

Input: `biblioforge/data/raw/Stampa_Libri_Interni_RAW.xlsx`
Output: `biblioforge/data/cleaned/books_cleaned.xlsx`

## Error Handling

The script includes:

- Input file existence checks
- Missing value handling (NaN)
- Multiple-separator handling during split
- Automatic output-folder creation
- Global try/except with full traceback

## Processing Stats

The input file contains 2526 records, which are processed and saved in the cleaned output file.

## Example Output

```text
[1/9] Reading raw Excel file...
    > Loaded 2526 records

[2/9] Renaming columns...
    > Column 'Q.t' renamed to 'Quantità'

[3/9] Splitting TITOLO - AUTORE...
    > Column 'TITOLO - AUTORE' split into 'Titolo' and 'Autore'

[4/9] Trimming extra whitespace (strip)...
    > Whitespace removed from 5 text columns

[5/9] Formatting Prezzo column...
    > Prezzo formatted as EUR

[6/9] Converting Quantità to integer...
    > Quantità converted to integer

[7/9] Reordering columns...
    > Columns reordered

[8/9] Creating output folder...
    > Folder already exists: C:\...\biblioforge\data\cleaned

[9/9] Saving XLSX file...
    > File saved: C:\...\biblioforge\data\cleaned\books_cleaned.xlsx

CLEANING COMPLETED SUCCESSFULLY!
```

## Cleaned Data Sample

| Codice EAN | Cod. Ed. Int. | Titolo | Autore | EDITORE | Quantità | Prezzo |
|---|---|---|---|---|---|---|
| 9791280495488 | NaN | (SENZA) RESIDENZA | GARGIULO ENRICO | V-ERIS | 1 | EUR 6.90 |
| 9788822901637 | NaN | MELENCOLIA I DI DÜRER... | PANOFSKY ERWIN; SAXL... | v-quodlibet | 1 | EUR 24.00 |
| 9788804765332 | NaN | RECHERCHE DI PROUST... | RABONI GIOVANNI | V-MONDADORI | 1 | EUR 13.00 |

---

Project: BiblioForge  
Date: 2026  
Version: 1.0
