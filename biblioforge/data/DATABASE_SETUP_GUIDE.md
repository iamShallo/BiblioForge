# BiblioForge - Setup Database SQL Server

## 📋 Panoramica

Questa guida descrive come configurare e popolare il database SQL Server per BiblioForge partendo dal file Excel `books_cleaned.xlsx`.

---

## 🔧 Prerequisiti

### Software Richiesto:
1. **SQL Server** (2019 o superiore) - [Scarica](https://www.microsoft.com/it-it/sql-server/sql-server-downloads)
2. **SQL Server Management Studio** - [Scarica](https://learn.microsoft.com/it-it/sql/ssms/download-sql-server-management-studio-ssms)
3. **Python 3.8+** con le dipendenze (pandas, pyodbc, openpyxl)

### Installazione Dipendenze Python:
```bash
pip install -r requirements.txt
```

---

## 📝 STEP 1: Creare il Database in SQL Server

### 1.1 Aprire SQL Server Management Studio
- Avviare SSMS
- Connettersi al server locale (di solito `localhost` o `DESKTOP-XXXXX`)

### 1.2 Creare il Database
Eseguire il seguente comando SQL (selezionare "New Query"):

```sql
-- Creare il database BiblioForge
CREATE DATABASE BiblioForge;
GO

-- Selezionare il database
USE BiblioForge;
GO
```

### 1.3 Creare le Tabelle
Aprire il file `biblioforge/data/database_schema.sql` in SQL Management Studio e eseguire tutto il codice.

**Oppure copiare e incollare:**

```sql
USE BiblioForge;

-- Tabella Editori
CREATE TABLE Editori (
    EditorID INT IDENTITY(1,1) PRIMARY KEY,
    NomeEditore NVARCHAR(255) NOT NULL UNIQUE,
    DataCreazione DATETIME2 DEFAULT GETDATE(),
    DataModifica DATETIME2 DEFAULT GETDATE()
);

-- Tabella Autori
CREATE TABLE Autori (
    AutoreID INT IDENTITY(1,1) PRIMARY KEY,
    NomeAutore NVARCHAR(255) NOT NULL UNIQUE,
    DataCreazione DATETIME2 DEFAULT GETDATE(),
    DataModifica DATETIME2 DEFAULT GETDATE()
);

-- Tabella Libri
CREATE TABLE Libri (
    LibroID INT IDENTITY(1,1) PRIMARY KEY,
    CodiceEAN VARCHAR(50) UNIQUE,
    CodiceEditoreInterno INT NULL,
    Titolo NVARCHAR(500) NOT NULL,
    AutoreID INT NULL,
    EditorID INT NULL,
    Quantita INT DEFAULT 0,
    Prezzo DECIMAL(10, 2) NOT NULL,
    DataCreazione DATETIME2 DEFAULT GETDATE(),
    DataModifica DATETIME2 DEFAULT GETDATE(),
    Attivo BIT DEFAULT 1,
    
    CONSTRAINT FK_Libri_Autori FOREIGN KEY (AutoreID) REFERENCES Autori(AutoreID),
    CONSTRAINT FK_Libri_Editori FOREIGN KEY (EditorID) REFERENCES Editori(EditorID),
    INDEX IX_CodiceEAN (CodiceEAN),
    INDEX IX_Titolo (Titolo),
    INDEX IX_EditorID (EditorID),
    INDEX IX_AutoreID (AutoreID)
);

-- Tabella ImportLog
CREATE TABLE ImportLog (
    LogID INT IDENTITY(1,1) PRIMARY KEY,
    CodiceEAN VARCHAR(50),
    Titolo NVARCHAR(500),
    Autore NVARCHAR(255),
    Editore NVARCHAR(255),
    Stato NVARCHAR(50),
    Messaggio NVARCHAR(MAX),
    DataImportazione DATETIME2 DEFAULT GETDATE(),
    
    INDEX IX_Stato (Stato),
    INDEX IX_DataImportazione (DataImportazione)
);
```

---

## 🚀 STEP 2: Eseguire l'Importazione dei Dati

### 2.1 Preparazione dello Script
Aprire il file `biblioforge/data/import_to_database.py` e verificare/modificare:

```python
# Linea ~375
SERVER = "localhost"              # ⚠ Cambiare con il nome del vostro server
DATABASE = "BiblioForge"          # ✓ Mantenere uguale
EXCEL_FILE = "biblioforge/data/cleaned/books_cleaned.xlsx"  # ✓ Verificare il percorso
```

### 2.2 Trovare il Nome del Server
Se non siete certi del nome del server:

1. Aprire SQL Server Management Studio
2. Nella finestra di connessione, il nome del server è visibile
3. Esempi: `localhost`, `DESKTOP-XXXXX`, `SERVER-NAME`

### 2.3 Eseguire l'Importazione

**Da PowerShell:**
```powershell
cd C:\Users\claud\source\repos\BiblioForge
python biblioforge/data/import_to_database.py
```

**Output Atteso:**
```
======================================================================
BiblioForge - Database Importer
======================================================================

[1] Lettura del file Excel: biblioforge/data/cleaned/books_cleaned.xlsx
    ✓ Caricati 2526 record

[2] Inizio importazione nel database...
    Processati 100/2526 record...
    Processati 200/2526 record...
    ...
[3] Importazione completata!

======================================================================
STATISTICHE IMPORTAZIONE
======================================================================
Totali processati: 2526
✓ Inseriti: 2368
⊘ Duplicati: 0
⚠ Warning: 158
✗ Errori: 0
======================================================================
```

---

## 🔍 STEP 3: Verificare i Dati Importati

### 3.1 Query Rapida in SQL Management Studio

Eseguire il seguente codice SQL:

```sql
USE BiblioForge;

-- Contare i libri importati
SELECT COUNT(*) as TotaleLibri FROM Libri;

-- Vedere i primi 5 libri
SELECT TOP 5 
    Titolo, 
    (SELECT NomeAutore FROM Autori WHERE AutoreID = Libri.AutoreID) as Autore,
    (SELECT NomeEditore FROM Editori WHERE EditorID = Libri.EditorID) as Editore,
    Prezzo,
    Quantita
FROM Libri;

-- Statistiche
SELECT 
    COUNT(*) as TotaleLibri,
    COUNT(DISTINCT AutoreID) as TotaleAutori,
    COUNT(DISTINCT EditorID) as TotaleEditori,
    SUM(Quantita) as QuantitaTotale,
    AVG(Prezzo) as PrezzoMedio,
    SUM(Prezzo * Quantita) as ValoreTotaleInventario
FROM Libri;
```

### 3.2 Report Automatico Python

```bash
python biblioforge/data/database_queries.py
```

Output:
```
======================================================================
REPORT DATABASE BIBLIOFORGE
======================================================================

[1] STATISTICHE GENERALI
----------------------------------------------------------------------
  Totale Libri........................... 2,368
  Totale Autori.......................... 1,855
  Totale Editori......................... 282
  Quantità Totale........................ 3,015
  Valore Inventario (€)................. € 93,456.78

[2] TOP 10 EDITORI
----------------------------------------------------------------------
  V-EINAUDI                          Libri:   175, Qtà:  210, Prezzo medio:    25.50€
  V-MONDADORI                        Libri:   145, Qtà:  189, Prezzo medio:    18.30€
  ...

[3] LIBRI ESAURITI (Quantità = 0)
----------------------------------------------------------------------
  Totale libri esauriti: 1,200
  - Titolo Libro 1................................. € 15.99
  - Titolo Libro 2................................. € 22.50
  ...
```

---

## 🔧 Risoluzione dei Problemi

### Errore: "File not found"
```
✗ File non trovato: biblioforge/data/cleaned/books_cleaned.xlsx
```
**Soluzione:** 
1. Verificare che il file esista nel percorso corretto
2. Eseguire prima lo script di cleaning: `python biblioforge/data/clean_books.py`

### Errore: "Impossibile connettersi al database"
```
✗ Impossibile connettersi al database
Errore: Login failed for user
```
**Soluzioni:**
1. Verificare che SQL Server sia avviato (Services -> SQL Server)
2. Verificare il nome del server (controllare in SSMS)
3. Verificare che il database "BiblioForge" esista
4. Verificare le credenziali Windows (Trusted Connection)

### Errore: "Prezzo non valido"
```
WARNING: Prezzo non valido o mancante
```
**Causa:** Il campo Prezzo è vuoto o non in formato corretto
**Azione:** I record non validi vengono registrati in ImportLog con stato "WARNING"

### Errore: "DUPLICATE: EAN già presente"
```
DUPLICATE: EAN 9788822901637 già presente
```
**Causa:** Un libro con lo stesso EAN è già stato importato
**Azione:** Il record non viene inserito (idempotente)

---

## 📊 Struttura del Database

### Tabella: Libri
| Colonna | Tipo | Note |
|---------|------|------|
| LibroID | INT | Primary Key, Auto-incremento |
| CodiceEAN | VARCHAR(50) | UNIQUE, ISBN del libro |
| CodiceEditoreInterno | INT | Codice interno editore (nullable) |
| Titolo | NVARCHAR(500) | Titolo del libro (required) |
| AutoreID | INT | Foreign Key a Autori (nullable) |
| EditorID | INT | Foreign Key a Editori (nullable) |
| Quantita | INT | Quantità disponibile |
| Prezzo | DECIMAL(10,2) | Prezzo in Euro (2 decimali) |
| DataCreazione | DATETIME2 | Timestamp creazione |
| DataModifica | DATETIME2 | Timestamp ultima modifica |
| Attivo | BIT | Flag soft-delete (1=attivo, 0=cancellato) |

### Tabella: Autori
| Colonna | Tipo | Note |
|---------|------|------|
| AutoreID | INT | Primary Key, Auto-incremento |
| NomeAutore | NVARCHAR(255) | Nome univoco dell'autore |
| DataCreazione | DATETIME2 | Timestamp creazione |
| DataModifica | DATETIME2 | Timestamp ultima modifica |

### Tabella: Editori
| Colonna | Tipo | Note |
|---------|------|------|
| EditorID | INT | Primary Key, Auto-incremento |
| NomeEditore | NVARCHAR(255) | Nome univoco dell'editore |
| DataCreazione | DATETIME2 | Timestamp creazione |
| DataModifica | DATETIME2 | Timestamp ultima modifica |

### Tabella: ImportLog
| Colonna | Tipo | Note |
|---------|------|------|
| LogID | INT | Primary Key, Auto-incremento |
| CodiceEAN | VARCHAR(50) | EAN del libro (può essere NULL) |
| Titolo | NVARCHAR(500) | Titolo del libro |
| Autore | NVARCHAR(255) | Nome dell'autore |
| Editore | NVARCHAR(255) | Nome dell'editore |
| Stato | NVARCHAR(50) | SUCCESS, ERROR, DUPLICATE, WARNING |
| Messaggio | NVARCHAR(MAX) | Dettagli dell'operazione |
| DataImportazione | DATETIME2 | Timestamp dell'importazione |

---

## 🔐 Sicurezza e Best Practices

### ✅ Implementato nello Script:

1. **Validazione dei dati**: Verifica campi obbligatori e formati
2. **Gestione dei duplicati**: Controllo su CodiceEAN unico
3. **Transazioni**: Rollback automatico in caso di errore
4. **Normalizzazione**: Autori e Editori non duplicati
5. **Audit Trail**: Logging di tutte le operazioni
6. **Soft Delete**: Campo "Attivo" per cancellazioni logiche
7. **Indici**: Performance ottimizzate su ricerche frequenti
8. **Tipo DECIMAL**: Precisione per valori monetari

---

## 📚 Query Utili

### Cercare un Libro per Titolo
```sql
SELECT * FROM Libri 
WHERE Titolo LIKE '%Titolo Ricerca%' AND Attivo = 1;
```

### Cercare Libri di un Autore
```sql
SELECT l.* FROM Libri l
JOIN Autori a ON l.AutoreID = a.AutoreID
WHERE a.NomeAutore = 'Nome Autore' AND l.Attivo = 1;
```

### Libri per Editore
```sql
SELECT l.* FROM Libri l
JOIN Editori e ON l.EditorID = e.EditorID
WHERE e.NomeEditore = 'Nome Editore' AND l.Attivo = 1;
```

### Libri Esauriti (Quantità = 0)
```sql
SELECT Titolo, Prezzo FROM Libri 
WHERE Quantita = 0 AND Attivo = 1
ORDER BY Titolo;
```

### Top 10 Libri più Cari
```sql
SELECT TOP 10 Titolo, Prezzo FROM Libri 
WHERE Attivo = 1
ORDER BY Prezzo DESC;
```

### Statistiche per Editore
```sql
SELECT 
    e.NomeEditore,
    COUNT(*) as NumeroLibri,
    SUM(l.Quantita) as QuantitaTotale,
    AVG(l.Prezzo) as PrezzoMedio
FROM Libri l
JOIN Editori e ON l.EditorID = e.EditorID
WHERE l.Attivo = 1
GROUP BY e.NomeEditore
ORDER BY COUNT(*) DESC;
```

---

## 🆘 Supporto

Tutti gli errori e i dettagli delle operazioni vengono loggati in:
- `import_log.txt` - Log dei dettagli dell'importazione
- `ImportLog` (tabella SQL) - Log strutturato nel database

---

## 📅 Prossimi Passi

Dopo l'importazione, puoi:

1. **Connettere l'app al database** - Modificare il controller per usare SQL
2. **Creare una REST API** - Esporre i dati via API
3. **Aggiungere Autenticazione** - Proteggere i dati
4. **Implementare CRUD** - Gestire create/update/delete
5. **Aggiungere Validazioni** - Business logic nel database

---

**Documentazione aggiornata al:** 18 Marzo 2026

