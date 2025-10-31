import camelot
import pandas as pd
import os

# Define the input and output directories
pdf_directory = "pdfs_to_convert"
output_directory = "converted_csvs"

# Create the output directory if it doesn't exist
if not os.path.exists(output_directory):
    os.makedirs(output_directory)

def convert_pdf_to_csv(file_path):
    """
    Extracts tables from a PDF and saves them as CSV files.
    """
    try:
        # Extract tables from the PDF using Camelot's lattice method
        # The 'lattice' method works well for tables with clear grid lines.
        tables = camelot.read_pdf(file_path, pages='all', flavor='lattice')
        
        print(f"Found {tables.n} tables in {os.path.basename(file_path)}")

        # Check if any tables were found
        if tables.n > 0:
            for i, table in enumerate(tables):
                # Convert the table to a pandas DataFrame
                df = table.df
                
                # Create a filename for the CSV
                base_name = os.path.splitext(os.path.basename(file_path))[0]
                csv_filename = f"{base_name}_table_{i+1}.csv"
                output_path = os.path.join(output_directory, csv_filename)
                
                # Save the DataFrame to a CSV file
                df.to_csv(output_path, index=False)
                print(f"  -> Saved table {i+1} to {output_path}")
        else:
            print(f"  -> No tables found in {os.path.basename(file_path)}")

    except Exception as e:
        print(f"An error occurred while processing {file_path}: {e}")

# Process all PDF files in the specified directory
for filename in os.listdir(pdf_directory):
    if filename.lower().endswith(".pdf"):
        file_path = os.path.join(pdf_directory, filename)
        print(f"Processing: {filename}")
        convert_pdf_to_csv(file_path)

print("\nConversion process finished.")
