"""
BiblioForge - Data Cleaning Script
Script per pulire e trasformare il database di libri grezzo in formato strutturato.
"""

import os
import pandas as pd
from pathlib import Path


def clean_books_data(input_file: str, output_file: str) -> pd.DataFrame:
    """
    Legge il file Excel grezzo, applica trasformazioni e salva come XLSX.
    
    Args:
        input_file: Percorso del file Excel grezzo
        output_file: Percorso del file XLSX pulito
    
    Returns:
        DataFrame con i dati puliti
    """
    
    # Leggi il file Excel
    print("[1/8] Lettura del file Excel grezzo...")
    df = pd.read_excel(input_file)
    print(f"    > Caricati {len(df)} record")
    
    # Step 1: Rinomina colonne
    print("\n[2/8] Rinominazione colonne...")
    # La colonna Q.t ha caratteri speciali \xa0, la rinominiamo in Quantità
    # Usa il nome della colonna esatto da pandas
    old_col_name = [col for col in df.columns if 'Q.t' in col][0] if any('Q.t' in col for col in df.columns) else 'Q.t\xa0'
    df.rename(columns={old_col_name: 'Quantità'}, inplace=True)
    print(f"    > Colonna '{old_col_name}' rinominata a 'Quantità'")
    
    # Step 2: Split colonna TITOLO - AUTORE
    print("\n[3/8] Separazione TITOLO - AUTORE...")
    # Separa usando n=1 per gestire il caso di " - " multipli
    split_data = df['TITOLO - AUTORE'].str.split(' - ', n=1, expand=True)
    
    # Gestisci il caso in cui lo split produca meno di 2 colonne
    if len(split_data.columns) == 1:
        # Se non c'è " - ", assegna tutto al Titolo
        df['Titolo'] = split_data[0]
        df['Autore'] = ''
    else:
        df['Titolo'] = split_data[0]
        df['Autore'] = split_data[1]
    
    print(f"    > Colonna 'TITOLO - AUTORE' separata in 'Titolo' e 'Autore'")
    
    # Step 3: Pulizia spazi bianchi
    print("\n[4/8] Rimozione spazi superflui (strip)...")
    string_columns = df.select_dtypes(include=['object', 'string']).columns
    for col in string_columns:
        df[col] = df[col].str.strip()
    print(f"    > Spazi rimossi da {len(string_columns)} colonne di testo")
    
    # Step 4: Formattazione Prezzo con simbolo Euro
    print("\n[5/8] Formattazione colonna Prezzo...")
    # Converti a numerico e formatta con € 
    df['Prezzo'] = df['Prezzo'].apply(lambda x: f"EUR {x:.2f}" if pd.notna(x) else "")
    print("    > Prezzo formattato con simbolo Euro")
    
    # Step 5: Converti Quantità a intero (dove possibile)
    print("\n[6/8] Conversione Quantità a intero...")
    df['Quantità'] = df['Quantità'].fillna(0).astype(int)
    print("    > Quantità convertita a intero")
    
    # Step 6: Riordina le colonne in ordine logico
    print("\n[7/8] Riordino colonne...")
    columns_order = ['Codice EAN', 'Cod. Ed. Int.', 'Titolo', 'Autore', 
                     'EDITORE', 'Quantità', 'Prezzo']
    # Seleziona solo le colonne che esistono
    columns_to_keep = [col for col in columns_order if col in df.columns]
    df = df[columns_to_keep]
    print("    > Colonne riordinate")
    
    # Step 7: Crea la cartella output se non esiste
    print("\n[8/8] Creazione cartella output...")
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"    > Cartella creata: {output_dir}")
    else:
        print(f"    > Cartella già esistente: {output_dir}")
    
    # Step 9: Salva il file XLSX con encoding UTF-8 BOM per preservare i caratteri
    print("\n[9/9] Salvataggio file XLSX...")
    df.to_excel(output_file, index=False, sheet_name='Libri')
    print(f"    > File salvato: {output_file}")
    
    # Riepilogo
    print("\n" + "="*70)
    print("PULIZIA COMPLETATA CON SUCCESSO!")
    print("="*70)
    print(f"\nStatistiche:")
    print(f"  - Righe elaborate: {len(df)}")
    print(f"  - Colonne nel file finale: {len(df.columns)}")
    print(f"  - Colonne: {', '.join(df.columns)}")
    print(f"\nAnteprima dati puliti (prime 5 righe):")
    print(df.head().to_string())
    
    return df


def main():
    """Funzione principale per eseguire il script di pulizia."""
    
    # Percorsi dei file
    project_root = Path(__file__).parent
    input_file = project_root / 'biblioforge' / 'data' / 'raw' / 'Stampa_Libri_Interni_RAW.xlsx'
    output_file = project_root / 'biblioforge' / 'data' / 'cleaned' / 'books_cleaned.xlsx'
    
    # Verifica che il file input esista
    if not input_file.exists():
        print(f"ERRORE: File non trovato: {input_file}")
        return False
    
    try:
        # Esegui la pulizia
        clean_books_data(str(input_file), str(output_file))
        return True
    except Exception as e:
        print(f"ERRORE durante l'elaborazione: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)

