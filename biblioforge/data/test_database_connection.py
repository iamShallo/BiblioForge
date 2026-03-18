"""
BiblioForge - SQL Server Connection Tester
Script per verificare la connessione a SQL Server e il setup del database.
"""

import pyodbc
import sys


def test_connection(server: str, database: str = None) -> bool:
    """
    Testa la connessione a SQL Server.
    
    Args:
        server: Nome del server SQL
        database: Nome del database (opzionale)
        
    Returns:
        bool: True se connessione riuscita
    """
    try:
        if database:
            connection_string = f"""
            Driver={{ODBC Driver 17 for SQL Server}};
            Server={server};
            Database={database};
            Trusted_Connection=yes;
            """
        else:
            connection_string = f"""
            Driver={{ODBC Driver 17 for SQL Server}};
            Server={server};
            Trusted_Connection=yes;
            """
        
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()
        
        if database:
            cursor.execute("SELECT @@VERSION")
            version = cursor.fetchone()[0]
            print(f"✓ Connessione a '{server}' (DB: '{database}') riuscita!")
            print(f"  SQL Server: {version.split('-')[0].strip()}")
        else:
            cursor.execute("SELECT @@VERSION")
            version = cursor.fetchone()[0]
            print(f"✓ Connessione a '{server}' riuscita!")
            print(f"  SQL Server: {version.split('-')[0].strip()}")
        
        conn.close()
        return True
    
    except Exception as e:
        print(f"✗ Errore: {e}")
        return False


def list_databases(server: str) -> list:
    """
    Lista tutti i database presenti nel server.
    
    Args:
        server: Nome del server SQL
        
    Returns:
        list: Lista dei nomi dei database
    """
    try:
        connection_string = f"""
        Driver={{ODBC Driver 17 for SQL Server}};
        Server={server};
        Trusted_Connection=yes;
        """
        
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()
        cursor.execute("""
        SELECT name FROM sys.databases 
        WHERE name NOT IN ('master', 'model', 'msdb', 'tempdb')
        ORDER BY name
        """)
        
        databases = [row[0] for row in cursor.fetchall()]
        conn.close()
        return databases
    
    except Exception as e:
        print(f"Errore nel listare i database: {e}")
        return []


def check_database_tables(server: str, database: str) -> dict:
    """
    Verifica se il database ha tutte le tabelle richieste.
    
    Args:
        server: Nome del server SQL
        database: Nome del database
        
    Returns:
        dict: Stato delle tabelle
    """
    try:
        connection_string = f"""
        Driver={{ODBC Driver 17 for SQL Server}};
        Server={server};
        Database={database};
        Trusted_Connection=yes;
        """
        
        conn = pyodbc.connect(connection_string)
        cursor = conn.cursor()
        
        required_tables = ['Libri', 'Autori', 'Editori', 'ImportLog']
        table_status = {}
        
        for table in required_tables:
            cursor.execute(f"""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_NAME = '{table}'
            """)
            exists = cursor.fetchone()[0] > 0
            
            if exists:
                # Contare i record
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                table_status[table] = {'esiste': True, 'record': count}
            else:
                table_status[table] = {'esiste': False, 'record': 0}
        
        conn.close()
        return table_status
    
    except Exception as e:
        print(f"Errore nel verificare le tabelle: {e}")
        return {}


def main():
    """Funzione principale del tester."""
    
    print("\n" + "="*70)
    print("BiblioForge - SQL Server Connection Tester")
    print("="*70 + "\n")
    
    # Leggi i parametri
    server = input("Inserisci il nome del server SQL (default: localhost): ").strip() or "localhost"
    
    print(f"\n[1] Test connessione al server '{server}'...")
    print("-" * 70)
    
    if not test_connection(server):
        print("\n✗ Impossibile connettersi al server.")
        print("\nSuggerimenti:")
        print("1. Verificare che SQL Server sia avviato")
        print("2. Verificare il nome del server (controllare in SQL Management Studio)")
        print("3. Verificare le credenziali Windows (Trusted Connection)")
        return False
    
    # Lista database
    print("\n[2] Lista database disponibili...")
    print("-" * 70)
    databases = list_databases(server)
    
    if not databases:
        print("Nessun database trovato (oltre a master, model, msdb, tempdb)")
    else:
        for db in databases:
            print(f"  - {db}")
    
    # Test BiblioForge
    print(f"\n[3] Ricerca database 'BiblioForge'...")
    print("-" * 70)
    
    if 'BiblioForge' in databases:
        print("✓ Database 'BiblioForge' trovato!")
        
        # Verifica tabelle
        print(f"\n[4] Verifica struttura del database...")
        print("-" * 70)
        
        table_status = check_database_tables(server, 'BiblioForge')
        
        all_present = True
        for table, status in table_status.items():
            if status['esiste']:
                print(f"  ✓ {table:<15} ({status['record']:>6} record)")
            else:
                print(f"  ✗ {table:<15} (MANCANTE)")
                all_present = False
        
        if all_present:
            print(f"\n✓ Database completamente configurato!")
            print(f"  Pronto per l'importazione dei dati")
            print(f"\n  Eseguire: python biblioforge/data/import_to_database.py")
        else:
            print(f"\n✗ Database incompleto!")
            print(f"  Eseguire lo script SQL: database_schema.sql")
            print(f"  Oppure copiare il contenuto in SQL Management Studio")
    
    else:
        print("✗ Database 'BiblioForge' non trovato!")
        print("\nPer creare il database:")
        print("1. Aprire SQL Server Management Studio")
        print("2. Eseguire il comando:")
        print("   CREATE DATABASE BiblioForge;")
        print("3. Eseguire il file 'database_schema.sql'")
        print("4. Eseguire nuovamente questo script")
    
    print("\n" + "="*70 + "\n")
    
    return 'BiblioForge' in databases


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

