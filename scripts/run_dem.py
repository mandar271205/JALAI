import sys
import traceback

with open("dem_error.log", "w") as f:
    try:
        import jalrakshak_ml.pipelines.dem_pipeline
        jalrakshak_ml.pipelines.dem_pipeline.main()
    except Exception as e:
        f.write('ERROR:\n')
        traceback.print_exc(file=f)
        sys.exit(1)
