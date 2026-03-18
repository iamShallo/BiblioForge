"""
BiblioForge - Database Query Utilities
Script con query comuni per interrogare il database e troubleshooting.
"""

import pyodbc
import logging
from typing import List, Dict, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class DatabaseQueryHelper:
    """Classe helper per query comuni al database BiblioForge."""
    
    def __init__(self, server: str, database: str):
        """Inizializza il connettore."""
        self.server = server
        self.database = database
        self.connection = None
    
    def connect(self) -> bool:
        """Connette al database."""
        try:
            connection_string = f"""
            Driver={{ODBC Driver 17 for SQL Server}};
            Server={self.server};
            Database={self.database};
            Trusted_Connection=yes;
            """
            self.connection = pyodbc.connect(connection_string)
            return True
        except Exception as e:
            print(f"Errore di connessione: {e}")
            return False
    
    def execute_query(self, query: str) -> List[Dict]:
        """
        Esegue una query SELECT e ritorna i risultati come lista di dizionari.
        
        Args:
            query: Query SQL
            
        Returns:
            List[Dict]: Risultati della query
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute(query)
            
            # Ottieni i nomi delle colonne
            columns = [description[0] for description in cursor.description]
            
            # Costruisci la lista di dizionari
            results = []
            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))
            
            return results
        except Exception as e:
            print(f"Errore nella query: {e}")
            return []
    
    def get_database_info(self) -> Dict:
        """Ritorna informazioni sul database."""
        info = {}
        
        try:
            cursor = self.connection.cursor()
            
            # Numero di libri
            cursor.execute("SELECT COUNT(*) as count FROM Libri WHERE Attivo = 1")
            info['Totale Libri'] = cursor.fetchval()
            
            # Numero di autori
            cursor.execute("SELECT COUNT(*) as count FROM Autori")
            info['Totale Autori'] = cursor.fetchval()
            
            # Numero di editori
            cursor.execute("SELECT COUNT(*) as count FROM Editori")
            info['Totale Editori'] = cursor.fetchval()
            
            # Quantità totale
            cursor.execute("SELECT SUM(Quantita) as total FROM Libri WHERE Attivo = 1")
            info['Quantità Totale'] = cursor.fetchval() or 0
            
            # Valore totale inventario
            cursor.execute("SELECT SUM(Prezzo * Quantita) as total FROM Libri WHERE Attivo = 1")
            info['Valore Inventario (€)'] = float(cursor.fetchval() or 0)
            
        except Exception as e:
            print(f"Errore nel recupero info: {e}")
        
        return info
    
    def search_by_title(self, search_term: str, limit: int = 10) -> List[Dict]:
        """Cerca libri per titolo."""
        query = f"""
        SELECT TOP {limit} 
            l.LibroID, 
            l.Titolo, 
            a.NomeAutore, 
            e.NomeEditore, 
            l.Prezzo, 
            l.Quantita,
            l.CodiceEAN
        FROM Libri l
        LEFT JOIN Autori a ON l.AutoreID = a.AutoreID
        LEFT JOIN Editori e ON l.EditorID = e.EditorID
        WHERE l.Titolo LIKE '%{search_term}%' AND l.Attivo = 1
        ORDER BY l.Titolo
        """
        return self.execute_query(query)
    
    def search_by_author(self, author_name: str, limit: int = 10) -> List[Dict]:
        """Cerca libri per autore."""
        query = f"""
        SELECT TOP {limit}
            l.LibroID,
            l.Titolo,
            a.NomeAutore,
            e.NomeEditore,
            l.Prezzo,
            l.Quantita
        FROM Libri l
        LEFT JOIN Autori a ON l.AutoreID = a.AutoreID
        LEFT JOIN Editori e ON l.EditorID = e.EditorID
        WHERE a.NomeAutore LIKE '%{author_name}%' AND l.Attivo = 1
        ORDER BY l.Titolo
        """
        return self.execute_query(query)
    
    def search_by_publisher(self, publisher_name: str, limit: int = 10) -> List[Dict]:
        """Cerca libri per editore."""
        query = f"""
        SELECT TOP {limit}
            l.LibroID,
            l.Titolo,
            a.NomeAutore,
            e.NomeEditore,
            l.Prezzo,
            l.Quantita
        FROM Libri l
        LEFT JOIN Autori a ON l.AutoreID = a.AutoreID
        LEFT JOIN Editori e ON l.EditorID = e.EditorID
        WHERE e.NomeEditore LIKE '%{publisher_name}%' AND l.Attivo = 1
        ORDER BY l.Titolo
        """
        return self.execute_query(query)
    
    def get_top_publishers(self, limit: int = 10) -> List[Dict]:
        """Ritorna gli editori con più libri."""
        query = f"""
        SELECT TOP {limit}
            e.NomeEditore,
            COUNT(*) as NumeroLibri,
            SUM(l.Quantita) as QuantitaTotale,
            AVG(l.Prezzo) as PrezzoMedio
        FROM Libri l
        JOIN Editori e ON l.EditorID = e.EditorID
        WHERE l.Attivo = 1
        GROUP BY e.NomeEditore
        ORDER BY COUNT(*) DESC
        """
        return self.execute_query(query)
    
    def get_books_out_of_stock(self, limit: int = 20) -> List[Dict]:
        """Ritorna i libri esauriti (quantità 0)."""
        query = f"""
        SELECT TOP {limit}
            l.LibroID,
            l.Titolo,
            a.NomeAutore,
            e.NomeEditore,
            l.Prezzo
        FROM Libri l
        LEFT JOIN Autori a ON l.AutoreID = a.AutoreID
        LEFT JOIN Editori e ON l.EditorID = e.EditorID
        WHERE l.Quantita = 0 AND l.Attivo = 1
        ORDER BY l.Titolo
        """
        return self.execute_query(query)
    
    def get_expensive_books(self, min_price: float = 50.0, limit: int = 10) -> List[Dict]:
        """Ritorna i libri più cari."""
        query = f"""
        SELECT TOP {limit}
            l.LibroID,
            l.Titolo,
            a.NomeAutore,
            e.NomeEditore,
            l.Prezzo,
            l.Quantita
        FROM Libri l
        LEFT JOIN Autori a ON l.AutoreID = a.AutoreID
        LEFT JOIN Editori e ON l.EditorID = e.EditorID
        WHERE l.Prezzo >= {min_price} AND l.Attivo = 1
        ORDER BY l.Prezzo DESC
        """
        return self.execute_query(query)
    
    def get_import_log_summary(self) -> Dict:
        """Ritorna un riepilogo del log di importazione."""
        try:
            cursor = self.connection.cursor()
            results = {}
            
            # Conteggio per stato
            cursor.execute("""
            SELECT Stato, COUNT(*) as Numero
            FROM ImportLog
            GROUP BY Stato
            ORDER BY Stato
            """)
            
            for row in cursor.fetchall():
                results[row[0]] = row[1]
            
            return results
        except Exception as e:
            print(f"Errore nel recupero log: {e}")
            return {}
    
    def disconnect(self):
        """Chiude la connessione."""
        if self.connection:
            self.connection.close()


def print_database_report(server: str, database: str):
    """Stampa un report completo del database."""
    
    helper = DatabaseQueryHelper(server, database)
    
    if not helper.connect():
        print("Impossibile connettersi al database")
        return
    
    try:
        print("\n" + "="*70)
        print("REPORT DATABASE BIBLIOFORGE")
        print("="*70 + "\n")
        
        # Info generali
        print("[1] STATISTICHE GENERALI")
        print("-" * 70)
        info = helper.get_database_info()
        for key, value in info.items():
            if isinstance(value, float):
                print(f"  {key:.<40} € {value:,.2f}")
            else:
                print(f"  {key:.<40} {value:,}")
        
        # Top editori
        print("\n[2] TOP 10 EDITORI")
        print("-" * 70)
        publishers = helper.get_top_publishers(10)
        for pub in publishers:
            print(f"  {pub['NomeEditore']:<35} Libri: {pub['NumeroLibri']:>4}, " +
                  f"Qtà: {pub['QuantitaTotale']:>4}, Prezzo medio: € {pub['PrezzoMedio']:>8.2f}")
        
        # Libri esauriti
        print("\n[3] LIBRI ESAURITI (Quantità = 0)")
        print("-" * 70)
        out_of_stock = helper.get_books_out_of_stock(5)
        print(f"  Totale libri esauriti: {len(out_of_stock)}")
        for book in out_of_stock[:5]:
            print(f"  - {book['Titolo']:<50} € {book['Prezzo']:.2f}")
        
        # Libri più cari
        print("\n[4] LIBRI PIÙ CARI (> € 50)")
        print("-" * 70)
        expensive = helper.get_expensive_books(50.0, 5)
        for book in expensive:
            print(f"  {book['Prezzo']:>7.2f}€ - {book['Titolo']:<50}")
        
        # Log importazione
        print("\n[5] LOG IMPORTAZIONE")
        print("-" * 70)
        log_summary = helper.get_import_log_summary()
        for status, count in log_summary.items():
            print(f"  {status:.<40} {count:,}")
        
        print("\n" + "="*70 + "\n")
    
    finally:
        helper.disconnect()


if __name__ == "__main__":
    # Personalizza questi valori
    SERVER = r"(localdb)\MSSQLLocalDB"
    DATABASE = "BiblioForge"
    
    print_database_report(SERVER, DATABASE)

