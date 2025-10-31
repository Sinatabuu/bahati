import camelot
import os
import glob
import pandas as pd

# --- Configuration ---
# Set the input and output directories relative to the script's location
PDF_DIR = 'pdfs'
CSV_DIR = 'csv_output'

# The extraction method: 'lattice' (for lined tables) or 'stream' (for space-separated tables)
EXTRACTION_FLAVOR = 'lattice'

def convert_pdf_to_csv(pdf_path, output_dir):
    """Reads a PDF, extracts tables, and saves them as CSV files."""
    
    # Get the base name of the file (without extension) for naming output CSVs
    pdf_base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    
    print(f"\n--- Processing: {pdf_base_name}.pdf ---")
    
    try:
        # Use Camelot to read the PDF. 
        # pages='all' extracts from all pages.
        tables = camelot.read_pdf(
            pdf_path, 
            pages='all', 
            flavor=EXTRACTION_FLAVOR,
            # Adjust table_coords or columns here if default fails for complex PDFs
        )
        
        print(f"Found {tables.n} tables in total.")
        
        if tables.n == 0:
            print("No tables detected. Check the PDF quality or try changing EXTRACTION_FLAVOR to 'stream'.")
            return

        # Iterate through all detected tables and save each one
        for i, table in enumerate(tables):
            # Check for parsing errors
            if table.parsing_report['accuracy'] < 95.0:
                 print(f"Warning: Table {i+1} has low accuracy ({table.parsing_report['accuracy']:.2f}%). May need manual review.")

            output_file = os.path.join(output_dir, f'{pdf_base_name}_table_{i+1}.csv')
            
            # Convert the table to a Pandas DataFrame and save to CSV
            df = table.df
            df.to_csv(output_file, index=False)
            print(f"Saved Table {i+1} to: {output_file}")
            
    except Exception as e:
        print(f"An error occurred while processing {pdf_path}: {e}")


def main():
    # 1. Setup directories
    os.makedirs(PDF_DIR, exist_ok=True)
    os.makedirs(CSV_DIR, exist_ok=True)
    
    # 2. Find all PDF files in the input directory
    pdf_files = glob.glob(os.path.join(PDF_DIR, '*.pdf'))
    
    if not pdf_files:
        print(f"No PDF files found in the '{PDF_DIR}' directory. Please place your PDFs there.")
        return

    # 3. Process each PDF
    for pdf_file in pdf_files:
        convert_pdf_to_csv(pdf_file, CSV_DIR)

    print("\n--- Processing Complete ---")
    print(f"Check the '{CSV_DIR}' folder for your generated CSV files.")

if __name__ == "__main__":
    main()
