import pandas as pd
from pathlib import Path
import sqlite3

# 1. Define your base directories mapped to their target years
# Using the exact paths you provided
YEAR_FOLDERS = {
    2021: Path(r"C:\Users\{}\2021  report"),
    2022: Path(r"C:\Users\{}\2022"),
    2023: Path(r"C:\Users\{}\2023"),
    2024: Path(r"C:\Users\{}\2024 report")
}

# The exact 5 airports required for the dashboard
TARGET_AIRPORTS = ['HEATHROW', 'GATWICK', 'MANCHESTER', 'BIRMINGHAM', 'EDINBURGH']

def discover_csv_files(base_path):
    """
    Phase 1: Hunts down the required CSVs recursively inside monthly subfolders only.
    """
    def subfolder_only(files):
        return [f for f in files if f.parent != base_path]

    table_09_files  = subfolder_only(base_path.rglob('*09*.csv'))
    table_10_1_files = subfolder_only(base_path.rglob('*10*1*.csv'))
    table_10_2_files = subfolder_only(base_path.rglob('*10*2*.csv'))

    return table_09_files, table_10_1_files, table_10_2_files

def extract_and_filter(file_path, table_type, target_year):
    """
    Phase 2: Reads a single CSV, standardizes columns, 
    filters for the target airports, AND drops rogue years.
    """
    try:
        df = pd.read_csv(file_path)
        
        # Standardize Airport column
        if 'reporting_airport_name' in df.columns:
            df.rename(columns={'reporting_airport_name': 'Airport'}, inplace=True)
        elif 'rpt_apt_name' in df.columns:
            df.rename(columns={'rpt_apt_name': 'Airport'}, inplace=True)
            
        # Filter target airports
        if 'Airport' in df.columns:
            df = df[df['Airport'].isin(TARGET_AIRPORTS)].copy()
        else:
            return None
            
        # Extract Date
        if 'this_period' in df.columns:
            pass 
        elif 'This_Period' in df.columns:
            df.rename(columns={'This_Period': 'this_period'}, inplace=True)
            
        df['this_period'] = df['this_period'].astype(str)
        df['Year'] = df['this_period'].str[:4].astype(int)
        df['Month'] = df['this_period'].str[4:6].astype(int)
        
        # STRICT FILTER: Drop rows that don't match the target folder's year
        df = df[df['Year'] == target_year].copy()
        
        if df.empty:
            return None
            
        return df
        
    except Exception as e:
        print(f"Error processing {file_path.name}: {e}")
        return None

def clean_and_prepare(df, target_col, new_col_name):
    """
    Phase 3: Cleans the comma traps and standardizes the dataframe.
    """
    actual_col = None
    for col in df.columns:
        if col.lower() == target_col.lower():
            actual_col = col
            break
            
    if actual_col:
        df[new_col_name] = df[actual_col].astype(str).str.replace(',', '', regex=False)
        df[new_col_name] = pd.to_numeric(df[new_col_name], errors='coerce').fillna(0).astype(int)
    else:
        df[new_col_name] = 0
        
    return df[['Year', 'Month', 'Airport', new_col_name]]

# --- Main Execution Block ---
if __name__ == "__main__":
    
    # This list will hold the final merged dataframes for 2021, 2022, 2023, and 2024
    all_years_master_data = []
    
    # Loop through every year and folder path
    for current_year, folder_path in YEAR_FOLDERS.items():
        print(f"\n{'='*50}")
        print(f"PROCESSING YEAR: {current_year} -> {folder_path.name}")
        print(f"{'='*50}")
        
        if not folder_path.exists():
            print(f"Directory not found: {folder_path}. Skipping.")
            continue

        t09_files, t10_1_files, t10_2_files = discover_csv_files(folder_path)
        print(f"Found files -> T09: {len(t09_files)} | T10.1: {len(t10_1_files)} | T10.2: {len(t10_2_files)}")
        
        # Process Table 09
        all_t09 = [clean_and_prepare(df, 'total_pax_this_period', 'Total Passengers') 
                   for f in t09_files 
                   if (df := extract_and_filter(f, "Table 09", current_year)) is not None]
        master_09 = pd.concat(all_t09, ignore_index=True) if all_t09 else pd.DataFrame()
        
        # Process Table 10.1
        all_t10_1 = [clean_and_prepare(df, 'total_pax_tp', 'International Passengers') 
                     for f in t10_1_files 
                     if (df := extract_and_filter(f, "Table 10.1", current_year)) is not None]
        master_10_1 = pd.concat(all_t10_1, ignore_index=True) if all_t10_1 else pd.DataFrame()

        # Process Table 10.2
        all_t10_2 = [clean_and_prepare(df, 'total_pax_this_period', 'Domestic Passengers') 
                     for f in t10_2_files 
                     if (df := extract_and_filter(f, "Table 10.2", current_year)) is not None]
        master_10_2 = pd.concat(all_t10_2, ignore_index=True) if all_t10_2 else pd.DataFrame()

        # Merge the tables for the current year
        if not master_09.empty and not master_10_1.empty and not master_10_2.empty:
            yearly_master = pd.merge(master_09, master_10_1, on=['Year', 'Month', 'Airport'], how='outer')
            yearly_master = pd.merge(yearly_master, master_10_2, on=['Year', 'Month', 'Airport'], how='outer')
            
            yearly_master.fillna(0, inplace=True)
            for col in ['Total Passengers', 'International Passengers', 'Domestic Passengers']:
                yearly_master[col] = yearly_master[col].astype(int)
                
            all_years_master_data.append(yearly_master)
            print(f"Successfully compiled {len(yearly_master)} rows for {current_year}.")
        else:
            print(f"Skipping merge for {current_year} due to missing data.")

    # --- Final Compilation and Export ---
    print("\n" + "="*50)
    print("PHASE 5: FINAL COMPILATION & EXPORT")
    print("="*50)
    
    if all_years_master_data:
        # Concatenate all 4 years into one giant dataframe
        complete_dataset = pd.concat(all_years_master_data, ignore_index=True)
        
        # Sort everything perfectly by Date, then by Airport
        complete_dataset.sort_values(by=['Year', 'Month', 'Airport'], inplace=True)
        complete_dataset.reset_index(drop=True, inplace=True)
        
        # Define paths directly on your desktop
        desktop_path = Path(r"C:\Users\{}\Desktop")
        csv_path = desktop_path / "COMPLETE_aviation_dashboard.csv"
        db_path = desktop_path / "COMPLETE_aviation_dashboard.db"
        
        # Export to CSV
        complete_dataset.to_csv(csv_path, index=False)
        print(f"SUCCESS: Master CSV saved to {csv_path}")
        
        # Export to SQLite
        try:
            conn = sqlite3.connect(db_path)
            complete_dataset.to_sql('passenger_trends', conn, if_exists='replace', index=False)
            conn.close()
            print(f"SUCCESS: Master Database securely written to {db_path}")
        except Exception as e:
            print(f"Database Error: {e}")
            
        print(f"\nFINAL ROW COUNT: {len(complete_dataset)}")
        print("Target Validation: 4 years x 12 months x 5 airports = 240 rows.")
        if len(complete_dataset) == 240:
            print("PIPELINE STATUS: FLAWLESS. You are ready for EDA!")
    else:
        print("Critical Error: No data was compiled across any years.")