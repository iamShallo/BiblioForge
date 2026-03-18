"""BiblioForge data cleaning script."""

import os
import pandas as pd
from pathlib import Path


def clean_books_data(input_file: str, output_file: str) -> pd.DataFrame:
    """Read the raw Excel file, apply transformations, and save a cleaned XLSX."""
    
    # Read the raw Excel file.
    print("[1/9] Reading raw Excel file...")
    df = pd.read_excel(input_file)
    print(f"    > Loaded {len(df)} records")
    
    # Step 1: Rename columns.
    print("\n[2/9] Renaming columns...")
    # The Q.t column may contain special characters (\xa0), so we detect it safely.
    old_col_name = [col for col in df.columns if 'Q.t' in col][0] if any('Q.t' in col for col in df.columns) else 'Q.t\xa0'
    df.rename(columns={old_col_name: 'Quantità'}, inplace=True)
    print(f"    > Column '{old_col_name}' renamed to 'Quantità'")
    
    # Step 2: Split the TITOLO - AUTORE column.
    print("\n[3/9] Splitting TITOLO - AUTORE...")
    # Split with n=1 to handle multiple separators correctly.
    split_data = df['TITOLO - AUTORE'].str.split(' - ', n=1, expand=True)
    
    # Handle rows where the separator is missing.
    if len(split_data.columns) == 1:
        # If " - " is missing, keep full text in title.
        df['Titolo'] = split_data[0]
        df['Autore'] = ''
    else:
        df['Titolo'] = split_data[0]
        df['Autore'] = split_data[1]
    
    print("    > Column 'TITOLO - AUTORE' split into 'Titolo' and 'Autore'")
    
    # Step 3: Trim whitespace.
    print("\n[4/9] Trimming extra whitespace (strip)...")
    string_columns = df.select_dtypes(include=['object', 'string']).columns
    for col in string_columns:
        df[col] = df[col].str.strip()
    print(f"    > Whitespace removed from {len(string_columns)} text columns")
    
    # Step 4: Format price as EUR.
    print("\n[5/9] Formatting Prezzo column...")
    # Convert to numeric and format as EUR.
    df['Prezzo'] = df['Prezzo'].apply(lambda x: f"EUR {x:.2f}" if pd.notna(x) else "")
    print("    > Prezzo formatted as EUR")
    
    # Step 5: Convert Quantità to integer.
    print("\n[6/9] Converting Quantità to integer...")
    df['Quantità'] = df['Quantità'].fillna(0).astype(int)
    print("    > Quantità converted to integer")
    
    # Step 6: Reorder columns.
    print("\n[7/9] Reordering columns...")
    columns_order = ['Codice EAN', 'Cod. Ed. Int.', 'Titolo', 'Autore', 
                     'EDITORE', 'Quantità', 'Prezzo']
    # Keep only columns that exist.
    columns_to_keep = [col for col in columns_order if col in df.columns]
    df = df[columns_to_keep]
    print("    > Columns reordered")
    
    # Step 7: Create output folder if needed.
    print("\n[8/9] Creating output folder...")
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"    > Folder created: {output_dir}")
    else:
        print(f"    > Folder already exists: {output_dir}")
    
    # Step 8: Save XLSX output.
    print("\n[9/9] Saving XLSX file...")
    df.to_excel(output_file, index=False, sheet_name='Libri')
    print(f"    > File saved: {output_file}")
    
    # Summary
    print("\n" + "="*70)
    print("CLEANING COMPLETED SUCCESSFULLY!")
    print("="*70)
    print("\nStatistics:")
    print(f"  - Rows processed: {len(df)}")
    print(f"  - Columns in final file: {len(df.columns)}")
    print(f"  - Columns: {', '.join(df.columns)}")
    print("\nPreview of cleaned data (first 5 rows):")
    print(df.head().to_string())
    
    return df


def main():
    """Main entrypoint for the cleaning script."""
    
    # File paths
    project_root = Path(__file__).parent
    input_file = project_root / 'raw' / 'Stampa_Libri_Interni_RAW.xlsx'
    output_file = project_root / 'cleaned' / 'books_cleaned.xlsx'
    
    # Validate input file existence
    if not input_file.exists():
        print(f"ERROR: File not found: {input_file}")
        return False
    
    try:
        # Run cleaning
        clean_books_data(str(input_file), str(output_file))
        return True
    except Exception as e:
        print(f"ERROR during processing: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)

