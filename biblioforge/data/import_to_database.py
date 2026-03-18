"""
BiblioForge - Database Importer
Script per importare il file Excel cleaned in SQL Server in modo sicuro.
Gestisce errori, duplicati e validazione dei dati.
"""

import os
import sys
import logging
import pandas as pd
import pyodbc
from pathlib import Path
from datetime import datetime
from typing import Tuple, Optional, Dict
from decimal import Decimal

# =============================================================================
# CONFIGURAZIONE LOGGING
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('import_log.txt'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class DatabaseImporter:
    """
    Classe per gestire l'importazione sicura dei dati da Excel a SQL Server.
    Incluse validazione, gestione errori e prevenzione duplicati.
    """
    
    def __init__(self, server: str, database: str, driver: str = "ODBC Driver 17 for SQL Server"):
        """
        Inizializza il connettore database.
        
        Args:
            server: Nome del server SQL (es. "localhost" o "DESKTOP-ABC123")
            database: Nome del database (es. "BiblioForge")
            driver: Driver ODBC (default: SQL Server 2019+)
        """
        self.server = server
        self.database = database
        self.driver = driver
        self.connection = None
        self.stats = {
            'totali': 0,
            'inseriti': 0,
            'duplicati': 0,
            'errori': 0,
            'warning': 0
        }
    
    def connect(self) -> bool:
        """
        Connette al database SQL Server.
        
        Returns:
            bool: True se connessione riuscita, False altrimenti
        """
        try:
            connection_string = f"""
            Driver={{{self.driver}}};
            Server={self.server};
            Database={self.database};
            Trusted_Connection=yes;
            """
            
            self.connection = pyodbc.connect(connection_string)
            self.connection.setdecoding(pyodbc.SQL_CHAR, encoding='utf-8')
            self.connection.setdecoding(pyodbc.SQL_WCHAR, encoding='utf-8')
            self.connection.setencoding(encoding='utf-8')
            
            logger.info(f"[OK] Connessione a {self.server}.{self.database} riuscita")
            return True
        
        except pyodbc.Error as e:
            logger.error(f"[ERR] Errore di connessione: {e}")
            logger.error("SUGGERIMENTO: Verificare che SQL Server sia avviato e il database esista")
            return False
    
    def disconnect(self):
        """Chiude la connessione al database."""
        if self.connection:
            self.connection.close()
            logger.info("Connessione chiusa")
    
    def extract_numeric_price(self, price_str: str) -> Optional[Decimal]:
        """
        Estrae il valore numerico dal prezzo (es. "EUR 6.90" -> 6.90).
        
        Args:
            price_str: Stringa del prezzo
            
        Returns:
            Decimal: Prezzo come numero decimale, None se non valido
        """
        try:
            if pd.isna(price_str):
                return None
            
            # Rimuovi "EUR " e spazi
            price_clean = str(price_str).replace("EUR", "").strip()
            
            # Converti a Decimal per precisione monetaria
            price_decimal = Decimal(price_clean)
            
            return price_decimal
        
        except Exception as e:
            logger.warning(f"Errore nel parsing del prezzo '{price_str}': {e}")
            return None
    
    def get_or_create_autore(self, nome_autore: str) -> Optional[int]:
        """
        Recupera o crea un autore nel database (upsert).
        Gestisce i casi di NULL.
        
        Args:
            nome_autore: Nome dell'autore
            
        Returns:
            int: AutoreID, None se fallisce
        """
        try:
            # Se l'autore è nullo o vuoto
            if pd.isna(nome_autore) or nome_autore.strip() == "":
                return None
            
            nome_autore = nome_autore.strip()
            cursor = self.connection.cursor()
            
            # Verifica se l'autore esiste
            cursor.execute("SELECT AutoreID FROM Autori WHERE NomeAutore = ?", (nome_autore,))
            result = cursor.fetchone()
            
            if result:
                return result[0]
            
            # Altrimenti crea un nuovo autore
            cursor.execute(
                "INSERT INTO Autori (NomeAutore) VALUES (?)",
                (nome_autore,)
            )
            cursor.execute("SELECT @@IDENTITY as autore_id")
            autore_id = cursor.fetchone()[0]
            self.connection.commit()
            
            logger.debug(f"Autore creato: {nome_autore} (ID: {autore_id})")
            return autore_id
        
        except Exception as e:
            logger.warning(f"Errore nel gestire autore '{nome_autore}': {e}")
            self.connection.rollback()
            return None
    
    def get_or_create_editore(self, nome_editore: str) -> Optional[int]:
        """
        Recupera o crea un editore nel database (upsert).
        Gestisce i casi di NULL.
        
        Args:
            nome_editore: Nome dell'editore
            
        Returns:
            int: EditorID, None se fallisce
        """
        try:
            # Se l'editore è nullo o vuoto
            if pd.isna(nome_editore) or nome_editore.strip() == "":
                return None
            
            nome_editore = nome_editore.strip()
            cursor = self.connection.cursor()
            
            # Verifica se l'editore esiste
            cursor.execute("SELECT EditorID FROM Editori WHERE NomeEditore = ?", (nome_editore,))
            result = cursor.fetchone()
            
            if result:
                return result[0]
            
            # Altrimenti crea un nuovo editore
            cursor.execute(
                "INSERT INTO Editori (NomeEditore) VALUES (?)",
                (nome_editore,)
            )
            cursor.execute("SELECT @@IDENTITY as editor_id")
            editor_id = cursor.fetchone()[0]
            self.connection.commit()
            
            logger.debug(f"Editore creato: {nome_editore} (ID: {editor_id})")
            return editor_id
        
        except Exception as e:
            logger.warning(f"Errore nel gestire editore '{nome_editore}': {e}")
            self.connection.rollback()
            return None
    
    def libro_exists(self, codice_ean: str) -> bool:
        """
        Verifica se un libro esiste già nel database.
        
        Args:
            codice_ean: Codice EAN del libro
            
        Returns:
            bool: True se esiste, False altrimenti
        """
        try:
            if pd.isna(codice_ean) or codice_ean.strip() == "":
                return False
            
            cursor = self.connection.cursor()
            cursor.execute("SELECT 1 FROM Libri WHERE CodiceEAN = ?", (codice_ean.strip(),))
            return cursor.fetchone() is not None
        
        except Exception as e:
            logger.warning(f"Errore nella verifica duplicato: {e}")
            return False
    
    def insert_libro(self, row: pd.Series) -> Tuple[bool, str]:
        """
        Inserisce un singolo libro nel database con validazione completa.
        
        Args:
            row: Una riga del DataFrame (pd.Series)
            
        Returns:
            Tuple[bool, str]: (successo, messaggio)
        """
        try:
            # Estrazione e validazione dei dati
            codice_ean = str(row['Codice EAN']).strip() if pd.notna(row['Codice EAN']) else None
            cod_editore_int = int(row['Cod. Ed. Int.']) if pd.notna(row['Cod. Ed. Int.']) else None
            titolo = str(row['Titolo']).strip() if pd.notna(row['Titolo']) else ""
            autore = str(row['Autore']).strip() if pd.notna(row['Autore']) else None
            editore = str(row['EDITORE']).strip() if pd.notna(row['EDITORE']) else None
            quantita = int(row['Quantità']) if pd.notna(row['Quantità']) else 0
            prezzo = self.extract_numeric_price(row['Prezzo'])
            
            # Validazione campi obbligatori
            if not titolo or titolo == "":
                self.stats['warning'] += 1
                return False, "WARNING: Titolo mancante"
            
            if prezzo is None or prezzo <= 0:
                self.stats['warning'] += 1
                return False, "WARNING: Prezzo non valido o mancante"
            
            # Verifica duplicato su EAN (se presente)
            if codice_ean:
                if self.libro_exists(codice_ean):
                    self.stats['duplicati'] += 1
                    return False, f"DUPLICATE: EAN {codice_ean} già presente"
            
            # Recupera o crea Autore ed Editore
            autore_id = self.get_or_create_autore(autore)
            editor_id = self.get_or_create_editore(editore)
            
            # Inserimento del libro
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT INTO Libri (CodiceEAN, CodiceEditoreInterno, Titolo, AutoreID, 
                                   EditorID, Quantita, Prezzo)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (codice_ean, cod_editore_int, titolo, autore_id, editor_id, quantita, float(prezzo)))
            
            self.connection.commit()
            self.stats['inseriti'] += 1
            
            return True, f"SUCCESS: Libro '{titolo}' inserito"
        
        except Exception as e:
            self.stats['errori'] += 1
            self.connection.rollback()
            return False, f"ERROR: {str(e)}"
    
    def import_from_excel(self, excel_path: str, batch_size: int = 100) -> bool:
        """
        Importa i dati dal file Excel al database.
        
        Args:
            excel_path: Percorso del file Excel
            batch_size: Numero di record per batch (per performance)
            
        Returns:
            bool: True se completato, False se errore critico
        """
        try:
            # Leggi il file Excel
            logger.info(f"[1] Lettura del file Excel: {excel_path}")
            df = pd.read_excel(excel_path)
            logger.info(f"    [OK] Caricati {len(df)} record")
            
            self.stats['totali'] = len(df)
            
            # Processa ogni riga
            logger.info(f"[2] Inizio importazione nel database...")
            for idx, (index, row) in enumerate(df.iterrows(), 1):
                success, message = self.insert_libro(row)
                
                # Log ogni 100 record
                if idx % batch_size == 0 or idx == 1:
                    logger.info(f"    Processati {idx}/{len(df)} record...")
                
                # Registra nel log di importazione per tracking
                self.log_import(row, success, message)
            
            logger.info(f"[3] Importazione completata!")
            return True
        
        except Exception as e:
            logger.error(f"✗ Errore critico durante l'importazione: {e}")
            return False
    
    def log_import(self, row: pd.Series, success: bool, message: str):
        """
        Registra ogni operazione di importazione nel database.
        
        Args:
            row: Riga del DataFrame
            success: Se l'operazione è riuscita
            message: Messaggio di dettaglio
        """
        try:
            # Determina lo stato
            if "ERROR" in message:
                status = "ERROR"
            elif "DUPLICATE" in message:
                status = "DUPLICATE"
            elif "WARNING" in message:
                status = "WARNING"
            else:
                status = "SUCCESS"
            
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT INTO ImportLog (CodiceEAN, Titolo, Autore, Editore, Stato, Messaggio)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                str(row['Codice EAN']) if pd.notna(row['Codice EAN']) else None,
                str(row['Titolo']),
                str(row['Autore']) if pd.notna(row['Autore']) else None,
                str(row['EDITORE']) if pd.notna(row['EDITORE']) else None,
                status,
                message
            ))
            self.connection.commit()
        
        except Exception as e:
            logger.warning(f"Errore nel logging: {e}")
    
    def print_statistics(self):
        """Stampa un riepilogo delle statistiche di importazione."""
        logger.info("\n" + "="*70)
        logger.info("STATISTICHE IMPORTAZIONE")
        logger.info("="*70)
        logger.info(f"Totali processati: {self.stats['totali']}")
        logger.info(f"[OK] Inseriti: {self.stats['inseriti']}")
        logger.info(f"[DUP] Duplicati: {self.stats['duplicati']}")
        logger.info(f"[WARN] Warning: {self.stats['warning']}")
        logger.info(f"[ERR] Errori: {self.stats['errori']}")
        logger.info("="*70)


def main():
    """Funzione principale per eseguire l'importazione."""
    
    # =========================================================================
    # CONFIGURAZIONE - DA PERSONALIZZARE
    # =========================================================================
    SERVER = r"(localdb)\MSSQLLocalDB"                    # Nome server SQL
    DATABASE = "BiblioForge"                # Nome database
    EXCEL_FILE = r"C:\Users\claud\source\repos\BiblioForge\biblioforge\data\cleaned\books_cleaned.xlsx"
    
    logger.info("\n" + "="*70)
    logger.info("BiblioForge - Database Importer")
    logger.info("="*70 + "\n")
    
    # Verifica che il file Excel esista
    if not os.path.exists(EXCEL_FILE):
        logger.error(f"[ERR] File non trovato: {EXCEL_FILE}")
        return False
    
    # Crea l'importatore
    importer = DatabaseImporter(SERVER, DATABASE)
    
    # Connetti al database
    if not importer.connect():
        logger.error("[ERR] Impossibile connettersi al database")
        logger.error("\nPASSI PER RISOLVERE:")
        logger.error("1. Verificare che SQL Server sia avviato")
        logger.error("2. Verificare il nome del server (es. localhost, DESKTOP-ABC123)")
        logger.error("3. Verificare che il database 'BiblioForge' esista")
        logger.error("4. Eseguire il file database_schema.sql in SQL Management Studio")
        return False
    
    try:
        # Importa i dati
        success = importer.import_from_excel(EXCEL_FILE)
        
        # Stampa statistiche
        importer.print_statistics()
        
        return success
    
    finally:
        importer.disconnect()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

