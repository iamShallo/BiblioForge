-- =============================================================================
-- BiblioForge Database Schema
-- Database per la gestione della libreria
-- =============================================================================

-- Creare il database (eseguire manualmente in SQL Management Studio)
-- USE BiblioForge;

-- =============================================================================
-- TABELLA: Editori
-- Descrizione: Contiene i dati degli editori
-- =============================================================================
CREATE TABLE Editori (
    EditorID INT IDENTITY(1,1) PRIMARY KEY,
    NomeEditore NVARCHAR(255) NOT NULL UNIQUE,
    DataCreazione DATETIME2 DEFAULT GETDATE(),
    DataModifica DATETIME2 DEFAULT GETDATE()
);

-- =============================================================================
-- TABELLA: Autori
-- Descrizione: Contiene i dati degli autori
-- =============================================================================
CREATE TABLE Autori (
    AutoreID INT IDENTITY(1,1) PRIMARY KEY,
    NomeAutore NVARCHAR(255) NOT NULL UNIQUE,
    DataCreazione DATETIME2 DEFAULT GETDATE(),
    DataModifica DATETIME2 DEFAULT GETDATE()
);

-- =============================================================================
-- TABELLA: Libri
-- Descrizione: Contiene i dati principali dei libri
-- =============================================================================
CREATE TABLE Libri (
    LibroID INT IDENTITY(1,1) PRIMARY KEY,
    CodiceEAN VARCHAR(50) UNIQUE,                    -- ISBN/EAN - Chiave univoca
    CodiceEditoreInterno INT NULL,                  -- Codice interno dell'editore
    Titolo NVARCHAR(500) NOT NULL,                  -- Titolo del libro
    AutoreID INT NULL,                              -- Foreign Key a Autori
    EditorID INT NULL,                              -- Foreign Key a Editori
    Quantita INT DEFAULT 0,                         -- Quantità disponibile
    Prezzo DECIMAL(10, 2) NOT NULL,                 -- Prezzo in Euro
    DataCreazione DATETIME2 DEFAULT GETDATE(),
    DataModifica DATETIME2 DEFAULT GETDATE(),
    Attivo BIT DEFAULT 1,                           -- Flag per soft delete

    -- Foreign Keys
    CONSTRAINT FK_Libri_Autori FOREIGN KEY (AutoreID) REFERENCES Autori(AutoreID),
    CONSTRAINT FK_Libri_Editori FOREIGN KEY (EditorID) REFERENCES Editori(EditorID),

    -- Indici per performance
    INDEX IX_CodiceEAN (CodiceEAN),
    INDEX IX_Titolo (Titolo),
    INDEX IX_EditorID (EditorID),
    INDEX IX_AutoreID (AutoreID)
);

-- =============================================================================
-- TABELLA: ImportLog
-- Descrizione: Log di importazione per tracciare gli inserimenti e gli errori
-- =============================================================================
CREATE TABLE ImportLog (
    LogID INT IDENTITY(1,1) PRIMARY KEY,
    CodiceEAN VARCHAR(50),
    Titolo NVARCHAR(500),
    Autore NVARCHAR(255),
    Editore NVARCHAR(255),
    Stato NVARCHAR(50),                             -- 'SUCCESS', 'ERROR', 'DUPLICATE', 'WARNING'
    Messaggio NVARCHAR(MAX),                        -- Dettagli dell'operazione
    DataImportazione DATETIME2 DEFAULT GETDATE(),

    INDEX IX_Stato (Stato),
    INDEX IX_DataImportazione (DataImportazione)
);

-- =============================================================================
-- Commenti e Documentazione
-- =============================================================================
/*
SCHEMA DESIGN NOTES:
1. CodiceEAN è UNIQUE poiché rappresenta un libro unico (ISBN)
2. Autori e Editori sono normalizzati per evitare duplicati
3. Quantita e Prezzo sono stored come tipi numerici puri (INT e DECIMAL)
4. DataCreazione e DataModifica per audit trail
5. Attivo per soft delete (non eliminare fisicamente i record)
6. ImportLog per tracciare tutte le operazioni di import
7. Indici creati su colonne frequentemente interrogate

CONSIDERAZIONI:
- Prezzo è DECIMAL(10,2) per precisione monetaria
- Quantita è INT per numeri interi
- CodiceEditoreInterno può essere NULL se non disponibile
- Autori e Editori possono essere NULL per libri con dati incompleti
*/

