from pathlib import Path
from jalrakshak_ml.adapters.dem import CopernicusDEMAdapter

def main():
    print("Testing DEM adapter...")
    bbox = [72.75, 18.85, 73.0, 19.1]  # Mumbai bbox
    adapter = CopernicusDEMAdapter()
    
    print("Fetching...")
    output = Path("test_dem_output.tif")
    adapter.fetch(bbox_wgs84=bbox, output_path=output)
    print("Done! File at:", output)

if __name__ == "__main__":
    main()
