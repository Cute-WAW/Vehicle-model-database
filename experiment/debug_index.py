import sys
from pathlib import Path
script_dir = Path(__file__).parent.parent
sys.path.insert(0, str(script_dir / 'src'))
import os
os.chdir(script_dir)

import pandas as pd
from residual_data_index_step5 import ResidualDataIndex

def main():
    print("Inspect ResidualDataIndex...")
    index = ResidualDataIndex()
    index.build_from_csv(str(Path('output/residual_value_data_for_build_model.csv').absolute()))
    
    print(f"Total records: {len(index.records)}")
    print(f"Brand series keys: {len(index.brand_series_index)}")
    print(f"Vehicle type keys: {len(index.vehicle_type_index)}")
    
    # Check top vehicle types and counts
    print("\nTop 10 Vehicle Types:")
    sorted_types = sorted(index.vehicle_type_index.items(), key=lambda x: len(x[1]), reverse=True)[:10]
    for vt, indices in sorted_types:
        print(f"Type: '{vt}', Count: {len(indices)}")
        
    # Check random sample for vehicle_type field
    print("\nSample records check:")
    for i in range(5):
        r = index.records[i]
        print(f"Record {i}: Name='{r.vehicle_full_name}', Type='{r.vehicle_type}'")

if __name__ == '__main__':
    main()
