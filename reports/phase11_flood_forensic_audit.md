# phase11 flood forensic audit

```json
{
  "audit_version": "phase11_flood_forensic_v1",
  "status": "QUARANTINED_FOR_SPATIAL_TRAINING",
  "phase10_report_sha256": "20abffacf646376dfd36b53513c1203aba52c118fc649f1a4c4d4447602ac3dd",
  "runs": [
    {
      "scenario_id": "scenario_01_low_steady",
      "solver_success": true,
      "issues": [
        "ASCII_SQUARE_GRID_MISLABELED_AS_CANONICAL_RECTANGULAR_GRID",
        "FORCING_ENDS_BEFORE_SIMULATION_END"
      ],
      "source_type": "generated_physics_scenario",
      "solver_version": "LISFLOOD-FP version 8.0.3 (double)",
      "runtime_seconds": 98.56097940000473,
      "export_grid": {
        "shape": [
          256,
          256
        ],
        "crs": "EPSG:32643",
        "transform": [
          125.68115879274046,
          0.0,
          262927.81415520643,
          0.0,
          -196.08178669331937,
          2135557.2463123174
        ]
      },
      "export_values_match_ascii": true,
      "config_sha256": "48a17c39c7dab07b75fc7937d7f3aea2bda48dda237351b34d597aad50c34c2f",
      "forcing_file_sha256": "3d9d6891a540b058dfdf2bf81f464bb8c630ac103935f909396c6292570b769b",
      "output_sha256": "a5be8d624c35a85e03acb13b795b903a1d6b294efa696fde34aacedfab8b6d4c",
      "mass_sha256": "d7542c59e165f65011dae266c81f403740dabcb49673dde1598136df949b11c4",
      "config_hash_matches_record": true,
      "solver_grid_transform": [
        125.6812,
        0.0,
        262927.8142,
        0.0,
        -125.6812,
        2117534.6961000003
      ],
      "grid_matches_export": false,
      "forcing_conversion_correct": true,
      "source_rates_mm_h": [
        15.0,
        15.0
      ],
      "source_times_s": [
        0.0,
        1800.0
      ],
      "solver_rates_mm_h": [
        15.0,
        15.0
      ],
      "solver_times_s": [
        0.0,
        1800.0
      ],
      "sim_time_s": 3600.0,
      "depth_valid": true,
      "max_depth_m": 0.640999972820282,
      "wet_cells": 2021,
      "saved_depth_times_s": [
        0.0,
        1800.0,
        3600.0
      ],
      "target_semantics": "maximum_over_simulation",
      "mass_final_time_s": 3600.0,
      "mass_final_rain_minus_losses_m3": 15527867.8754,
      "roughness_used": {
        "type": "uniform_assumption",
        "manning_n": 0.04
      },
      "raster_roughness_used": false,
      "tidal_boundary_used": false,
      "exact_command_recorded": false,
      "calibrated": false,
      "eligible_for_canonical_training": false
    },
    {
      "scenario_id": "scenario_02_mod_steady",
      "solver_success": true,
      "issues": [
        "ASCII_SQUARE_GRID_MISLABELED_AS_CANONICAL_RECTANGULAR_GRID",
        "FORCING_ENDS_BEFORE_SIMULATION_END"
      ],
      "source_type": "generated_physics_scenario",
      "solver_version": "LISFLOOD-FP version 8.0.3 (double)",
      "runtime_seconds": 37.684586500006844,
      "export_grid": {
        "shape": [
          256,
          256
        ],
        "crs": "EPSG:32643",
        "transform": [
          125.68115879274046,
          0.0,
          262927.81415520643,
          0.0,
          -196.08178669331937,
          2135557.2463123174
        ]
      },
      "export_values_match_ascii": true,
      "config_sha256": "cd3e8e7af0b6bcdbfa649171617e59c7e78b20e4880bf964ff4f444d4ad80927",
      "forcing_file_sha256": "1f994e9247a0c7d745d035677913f9f57567047eb744886999404b2b1fedf9f5",
      "output_sha256": "68b8e58f435370c5ff164c4bbd115ab43cc64a31feddc6324cb19f036bdb98a2",
      "mass_sha256": "cd8e85ef91a157dfadead6a957c878cf0245736c9bda064174313267cd1fc179",
      "config_hash_matches_record": true,
      "solver_grid_transform": [
        125.6812,
        0.0,
        262927.8142,
        0.0,
        -125.6812,
        2117534.6961000003
      ],
      "grid_matches_export": false,
      "forcing_conversion_correct": true,
      "source_rates_mm_h": [
        35.0,
        35.0
      ],
      "source_times_s": [
        0.0,
        1800.0
      ],
      "solver_rates_mm_h": [
        35.0,
        35.0
      ],
      "solver_times_s": [
        0.0,
        1800.0
      ],
      "sim_time_s": 3600.0,
      "depth_valid": true,
      "max_depth_m": 2.1059999465942383,
      "wet_cells": 8268,
      "saved_depth_times_s": [
        0.0,
        1800.0,
        3600.0
      ],
      "target_semantics": "maximum_over_simulation",
      "mass_final_time_s": 3600.0,
      "mass_final_rain_minus_losses_m3": 36231691.7093,
      "roughness_used": {
        "type": "uniform_assumption",
        "manning_n": 0.04
      },
      "raster_roughness_used": false,
      "tidal_boundary_used": false,
      "exact_command_recorded": false,
      "calibrated": false,
      "eligible_for_canonical_training": false
    },
    {
      "scenario_id": "scenario_03_high_steady",
      "solver_success": true,
      "issues": [
        "ASCII_SQUARE_GRID_MISLABELED_AS_CANONICAL_RECTANGULAR_GRID",
        "FORCING_ENDS_BEFORE_SIMULATION_END"
      ],
      "source_type": "generated_physics_scenario",
      "solver_version": "LISFLOOD-FP version 8.0.3 (double)",
      "runtime_seconds": 51.778474599996116,
      "export_grid": {
        "shape": [
          256,
          256
        ],
        "crs": "EPSG:32643",
        "transform": [
          125.68115879274046,
          0.0,
          262927.81415520643,
          0.0,
          -196.08178669331937,
          2135557.2463123174
        ]
      },
      "export_values_match_ascii": true,
      "config_sha256": "1f5ced39e0e01543c728f4596f0cc02c762b1175cdd6055cf373f75ce8630a1d",
      "forcing_file_sha256": "06f324fc4c25ab998c6d3a6560be1d30fef7f04c075a75bb4604002813e28dbf",
      "output_sha256": "4bbe4e28704ce5dd14f5ccc59ded3a443cdf5494934ee5f0e913c638239d9b2c",
      "mass_sha256": "7878e4b67a51377506173c72e153d8cef95e85a03feea9360c7002f7044622ec",
      "config_hash_matches_record": true,
      "solver_grid_transform": [
        125.6812,
        0.0,
        262927.8142,
        0.0,
        -125.6812,
        2117534.6961000003
      ],
      "grid_matches_export": false,
      "forcing_conversion_correct": true,
      "source_rates_mm_h": [
        60.0,
        60.0
      ],
      "source_times_s": [
        0.0,
        1800.0
      ],
      "solver_rates_mm_h": [
        60.0,
        60.0
      ],
      "solver_times_s": [
        0.0,
        1800.0
      ],
      "sim_time_s": 3600.0,
      "depth_valid": true,
      "max_depth_m": 3.0139999389648438,
      "wet_cells": 32624,
      "saved_depth_times_s": [
        0.0,
        1800.0,
        3600.0
      ],
      "target_semantics": "maximum_over_simulation",
      "mass_final_time_s": 3600.0,
      "mass_final_rain_minus_losses_m3": 62111471.5017,
      "roughness_used": {
        "type": "uniform_assumption",
        "manning_n": 0.04
      },
      "raster_roughness_used": false,
      "tidal_boundary_used": false,
      "exact_command_recorded": false,
      "calibrated": false,
      "eligible_for_canonical_training": false
    },
    {
      "scenario_id": "scenario_04_front_loaded",
      "solver_success": true,
      "issues": [
        "ASCII_SQUARE_GRID_MISLABELED_AS_CANONICAL_RECTANGULAR_GRID",
        "FORCING_ENDS_BEFORE_SIMULATION_END"
      ],
      "source_type": "generated_physics_scenario",
      "solver_version": "LISFLOOD-FP version 8.0.3 (double)",
      "runtime_seconds": 54.151594700000715,
      "export_grid": {
        "shape": [
          256,
          256
        ],
        "crs": "EPSG:32643",
        "transform": [
          125.68115879274046,
          0.0,
          262927.81415520643,
          0.0,
          -196.08178669331937,
          2135557.2463123174
        ]
      },
      "export_values_match_ascii": true,
      "config_sha256": "7a87e25ad32ae9a83e007156297f6912c411b68e05242d1fcdd2578fd8ef4e56",
      "forcing_file_sha256": "9dca26d6297a8efeb40682d792fc4568cd9b91e3393ab697650ba94e670bf39a",
      "output_sha256": "d1f4e866d2bf0dd1aed235df98120ff74f1040b91344fb9c0f783d69e26de61e",
      "mass_sha256": "7a1d8f603c76c70dc50eab2a33dd3b83026a92b30371693a0e0bb43f4f38d4aa",
      "config_hash_matches_record": true,
      "solver_grid_transform": [
        125.6812,
        0.0,
        262927.8142,
        0.0,
        -125.6812,
        2117534.6961000003
      ],
      "grid_matches_export": false,
      "forcing_conversion_correct": true,
      "source_rates_mm_h": [
        80.0,
        20.0
      ],
      "source_times_s": [
        0.0,
        1800.0
      ],
      "solver_rates_mm_h": [
        80.0,
        20.0
      ],
      "solver_times_s": [
        0.0,
        1800.0
      ],
      "sim_time_s": 3600.0,
      "depth_valid": true,
      "max_depth_m": 2.4110000133514404,
      "wet_cells": 8585,
      "saved_depth_times_s": [
        0.0,
        1800.0,
        3600.0
      ],
      "target_semantics": "maximum_over_simulation",
      "mass_final_time_s": 3600.0,
      "mass_final_rain_minus_losses_m3": 36274824.6757,
      "roughness_used": {
        "type": "uniform_assumption",
        "manning_n": 0.04
      },
      "raster_roughness_used": false,
      "tidal_boundary_used": false,
      "exact_command_recorded": false,
      "calibrated": false,
      "eligible_for_canonical_training": false
    },
    {
      "scenario_id": "scenario_05_back_loaded",
      "solver_success": true,
      "issues": [
        "RAINFALL_COLUMNS_SWAPPED",
        "ASCII_SQUARE_GRID_MISLABELED_AS_CANONICAL_RECTANGULAR_GRID"
      ],
      "source_type": "generated_physics_scenario",
      "solver_version": "LISFLOOD-FP version 8.0.3 (double)",
      "runtime_seconds": 44.49938390000898,
      "export_grid": {
        "shape": [
          256,
          256
        ],
        "crs": "EPSG:32643",
        "transform": [
          125.68115879274046,
          0.0,
          262927.81415520643,
          0.0,
          -196.08178669331937,
          2135557.2463123174
        ]
      },
      "export_values_match_ascii": true,
      "config_sha256": "cc7d5f24260e3435a1d21b1224ef9ebad8ade94e3ee5743bc7a2b629d54f955c",
      "forcing_file_sha256": "b3c87534d808b2976a6f083e1e03c98b36ee6d319ee2197b064b56eeb8867141",
      "output_sha256": "04e387eef7971f18adf21bf3247be454d7b20ce050dc540e3cc19f540b5402d1",
      "mass_sha256": "03d67c3d59f7e5d7f687bf7a2429a0f71192f290e6c4b74af026b9f09e506f64",
      "config_hash_matches_record": true,
      "solver_grid_transform": [
        125.6812,
        0.0,
        262927.8142,
        0.0,
        -125.6812,
        2117534.6961000003
      ],
      "grid_matches_export": false,
      "forcing_conversion_correct": false,
      "source_rates_mm_h": [
        20.0,
        80.0
      ],
      "source_times_s": [
        0.0,
        1800.0
      ],
      "solver_rates_mm_h": [
        0.0,
        0.5
      ],
      "solver_times_s": [
        72000.0,
        288000.0
      ],
      "sim_time_s": 3600.0,
      "depth_valid": true,
      "max_depth_m": 0.0,
      "wet_cells": 0,
      "saved_depth_times_s": [
        0.0,
        1800.0,
        3600.0
      ],
      "target_semantics": "maximum_over_simulation",
      "mass_final_time_s": 3600.0,
      "mass_final_rain_minus_losses_m3": 0.0,
      "roughness_used": {
        "type": "uniform_assumption",
        "manning_n": 0.04
      },
      "raster_roughness_used": false,
      "tidal_boundary_used": false,
      "exact_command_recorded": false,
      "calibrated": false,
      "BACK_LOADED_SCENARIO_AUDITED": true,
      "BACK_LOADED_ZERO_DEPTH_EXPLAINED": true,
      "BACK_LOADED_ZERO_DEPTH_CAUSE": "rate/time columns swapped: forcing starts at 20 hours, after 1-hour sim_time; mass file records zero rainfall",
      "eligible_for_canonical_training": false
    },
    {
      "scenario_id": "scenario_06_short_intense",
      "solver_success": true,
      "issues": [
        "ASCII_SQUARE_GRID_MISLABELED_AS_CANONICAL_RECTANGULAR_GRID",
        "FORCING_ENDS_BEFORE_SIMULATION_END"
      ],
      "source_type": "generated_physics_scenario",
      "solver_version": "LISFLOOD-FP version 8.0.3 (double)",
      "runtime_seconds": 57.68299390000175,
      "export_grid": {
        "shape": [
          256,
          256
        ],
        "crs": "EPSG:32643",
        "transform": [
          125.68115879274046,
          0.0,
          262927.81415520643,
          0.0,
          -196.08178669331937,
          2135557.2463123174
        ]
      },
      "export_values_match_ascii": true,
      "config_sha256": "a7be8865b946029c0923085058a3446b8dce5ac16fdb002a45f7eca1ecd5e704",
      "forcing_file_sha256": "01d216a6511b5d963a2ce1cbc32d3fc8778bdc3f5e7379754bca1eef3a5bb88d",
      "output_sha256": "3e696439edc01935369eff666b37197e0e0a76105ff55e5009ebdebc27dc48c7",
      "mass_sha256": "a4061bbbfd74839ac446b8a3f0cf02774d0bfc14dfef7369ad723ade5eefcd77",
      "config_hash_matches_record": true,
      "solver_grid_transform": [
        125.6812,
        0.0,
        262927.8142,
        0.0,
        -125.6812,
        2117534.6961000003
      ],
      "grid_matches_export": false,
      "forcing_conversion_correct": true,
      "source_rates_mm_h": [
        90.0,
        45.0
      ],
      "source_times_s": [
        0.0,
        1800.0
      ],
      "solver_rates_mm_h": [
        90.0,
        45.0
      ],
      "solver_times_s": [
        0.0,
        1800.0
      ],
      "sim_time_s": 3600.0,
      "depth_valid": true,
      "max_depth_m": 2.989000082015991,
      "wet_cells": 31769,
      "saved_depth_times_s": [
        0.0,
        1800.0,
        3600.0
      ],
      "target_semantics": "maximum_over_simulation",
      "mass_final_time_s": 3600.0,
      "mass_final_rain_minus_losses_m3": 58261854.2576,
      "roughness_used": {
        "type": "uniform_assumption",
        "manning_n": 0.04
      },
      "raster_roughness_used": false,
      "tidal_boundary_used": false,
      "exact_command_recorded": false,
      "calibrated": false,
      "eligible_for_canonical_training": false
    }
  ],
  "genuine_solver_runs": 6,
  "canonical_training_eligible": 0,
  "BACK_LOADED_SCENARIO_AUDITED": true,
  "BACK_LOADED_ZERO_DEPTH_EXPLAINED": true,
  "BACK_LOADED_ZERO_DEPTH_CAUSE": "rate/time columns swapped: forcing starts at 20 hours, after 1-hour sim_time; mass file records zero rainfall",
  "OLD_PHASE10_GRID_GEOMETRY_VALID": false,
  "OLD_PHASE10_TRAINING_TARGETS_VERIFIED": false,
  "CORRECTED_SOLVER_GRID_VALID": true,
  "dataset": {
    "label": "SMALL PHYSICS SMOKE CORPUS",
    "train_scenarios": [
      "scenario_01_low_steady",
      "scenario_02_mod_steady",
      "scenario_03_high_steady",
      "scenario_04_front_loaded",
      "scenario_05_back_loaded"
    ],
    "validation_scenarios": [
      "scenario_06_short_intense"
    ],
    "scenario_split_isolated": true,
    "array_hashes_match": {
      "train_inputs": true,
      "train_targets": true,
      "val_inputs": true,
      "val_targets": true
    },
    "normalization_train_statistics_match": true,
    "normalization_ids_match": true,
    "maximum_depth_repeated_as_four_horizons": true,
    "ready": false
  },
  "limitations": [
    "Original arrays/checkpoint preserved for forensic reproducibility only.",
    "Uniform n=0.04 used; supplied roughness raster was hashed but not consumed.",
    "No tidal/open-coastal boundary file supplied; claimed coastal conditions unsupported.",
    "DEM repaired by nearest neighbor; roughness is OSM literature proxy, not ESA WorldCover.",
    "Raster row order preserved, but ASCII cell size and northing differ from canonical grid.",
    "Peak forcing channel discards temporal profile; one validation scenario cannot establish skill."
  ],
  "locked_rainfall_test_accessed": false,
  "corrected_diagnostic": {
    "scenario_id": "back_loaded_corrected_v1",
    "execution_status": "SUCCESS",
    "solver_binary": "wsl:/usr/local/bin/lisflood",
    "solver_version": "LISFLOOD-FP version 8.0.3 (double)",
    "exit_code": 0,
    "runtime_seconds": 39.71124889999919,
    "stdout_tail": "***************************\n LISFLOOD-FP version 8.0.3 (double)\nRectangular channels only.\n_CALCULATE_Q_MODE 1.\n***************************\n\nloop time 15.000000\n",
    "stderr_tail": "",
    "par_file_sha256": "649e05d0d8194f1cece4840319e70ecfefe919eaa5e9eebbadb17fb758c2aa9e",
    "dem_sha256": "348dfba78fe2713496db794d55051b531362e7b76c6e7d1c514f50fc9ab5c52a",
    "roughness_sha256": "305e91d8ef9b09abaaf88d0c62d8e75978706e1981a52827963b252ea913b038",
    "forcing_sha256": "27ffb5ebf4c0e78eab266fba4c8d7a8c9fa9a83d4c176b8f82c07c432ba9a88f",
    "output_files": [
      "data\\processed\\flood\\physics_outputs\\phase11_back_loaded_v2\\run\\results\\back_loaded_corrected_v1-0000.elev",
      "data\\processed\\flood\\physics_outputs\\phase11_back_loaded_v2\\run\\results\\back_loaded_corrected_v1-0000.wd",
      "data\\processed\\flood\\physics_outputs\\phase11_back_loaded_v2\\run\\results\\back_loaded_corrected_v1-0001.elev",
      "data\\processed\\flood\\physics_outputs\\phase11_back_loaded_v2\\run\\results\\back_loaded_corrected_v1-0001.wd",
      "data\\processed\\flood\\physics_outputs\\phase11_back_loaded_v2\\run\\results\\back_loaded_corrected_v1-0002.elev",
      "data\\processed\\flood\\physics_outputs\\phase11_back_loaded_v2\\run\\results\\back_loaded_corrected_v1-0002.wd",
      "data\\processed\\flood\\physics_outputs\\phase11_back_loaded_v2\\run\\results\\back_loaded_corrected_v1.dem",
      "data\\processed\\flood\\physics_outputs\\phase11_back_loaded_v2\\run\\results\\back_loaded_corrected_v1.inittm",
      "data\\processed\\flood\\physics_outputs\\phase11_back_loaded_v2\\run\\results\\back_loaded_corrected_v1.mass",
      "data\\processed\\flood\\physics_outputs\\phase11_back_loaded_v2\\run\\results\\back_loaded_corrected_v1.max",
      "data\\processed\\flood\\physics_outputs\\phase11_back_loaded_v2\\run\\results\\back_loaded_corrected_v1.maxtm",
      "data\\processed\\flood\\physics_outputs\\phase11_back_loaded_v2\\run\\results\\back_loaded_corrected_v1.mxe",
      "data\\processed\\flood\\physics_outputs\\phase11_back_loaded_v2\\run\\results\\back_loaded_corrected_v1.totaltm",
      "data\\processed\\flood\\physics_outputs\\phase11_back_loaded_v2\\run\\results\\back_loaded_corrected_v1_simulated_depth.tif"
    ],
    "max_depth_m": 1.399999976158142,
    "inundated_cells": 22210,
    "physically_simulated": true,
    "calibrated": false,
    "smoke_run": true,
    "created_at": "2026-09-09T22:42:33.092034+00:00",
    "mean_wet_depth_m": 0.07212035357952118,
    "depth_raster_path": "data\\processed\\flood\\physics_outputs\\phase11_back_loaded_v2\\run\\results\\back_loaded_corrected_v1_simulated_depth.tif",
    "diagnostic_only": true,
    "eligible_for_training": false,
    "source_type": "generated_physics_scenario",
    "source_dem_sha256": "129d7a6b98fafbf821d68f35ba1722a7531483511e602335a6dfbf85630be750",
    "solver_dem_sha256": "348dfba78fe2713496db794d55051b531362e7b76c6e7d1c514f50fc9ab5c52a",
    "solver_grid": {
      "shape": [
        256,
        165
      ],
      "transform": [
        196.08178669331937,
        0.0,
        262927.81415520643,
        0.0,
        -196.08178669331937,
        2135557.2463123174
      ],
      "crs": "EPSG:32643"
    },
    "forcing_integral_mm": 50.0,
    "original_phase10_outputs_modified": false,
    "roughness_used": "uniform n=0.04; raster not used",
    "boundary": "solver default; no tidal or coastal calibration",
    "command": [
      "wsl",
      "-d",
      "Ubuntu",
      "--",
      "bash",
      "-c",
      "cd <recorded work directory> && /usr/local/bin/lisflood back_loaded_corrected_v1.par"
    ],
    "work_directory": "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_back_loaded_v2\\run\\work",
    "manifest_sha256": "20d2aa8be44b82430686abecb755939558b08440a7b85f6c492ba4f8864dace4"
  },
  "solver_binary_evidence": {
    "verified": true,
    "command": [
      "wsl",
      "-d",
      "Ubuntu",
      "--",
      "/usr/local/bin/lisflood",
      "-version"
    ],
    "exit_code": 0,
    "stdout": "***************************\n LISFLOOD-FP version 8.0.3 (double)\nRectangular channels only.\n_CALCULATE_Q_MODE 1.\n***************************",
    "binary_sha256": "32c11fc6c40617bb283356c9405b116dce432e659ca7a2e796155d177a7e26da"
  },
  "corrected_corpus": {
    "status": "SMALL_PHYSICS_SMOKE_CORPUS",
    "manifest_path": "data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\sample_manifest.json",
    "manifest_sha256": "ceaca5707d6c3c1dce7fb854839825413f696cfc40f9cd37f5aeaa458ba0bd58",
    "dataset_dir": "data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\dataset",
    "dataset_reference_sha256": "40fd19e9157f7b8e5b8b2aae0947a19daa5d03f7f55aebd01335dbe1500cdd93",
    "normalization_sha256": "0aaf3db49ca4fb2e7be34c8740b3c39b0307ffef263a9f14d5b5efa4db1a4f9b",
    "train_scenarios": 5,
    "validation_scenarios": 1,
    "target_time_seconds": 3600,
    "shape": [
      256,
      164
    ],
    "FNO_TRAINING_EXECUTED": false,
    "limitations": [
      "SMALL PHYSICS SMOKE CORPUS",
      "Uniform uncalibrated roughness; dry initial condition.",
      "No explicit tidal boundary, infiltration, urban drains or calibrated channels.",
      "Actual final-depth targets at 60 minutes only; no 90/120 minute targets."
    ],
    "runs": [
      {
        "scenario_id": "scenario_01_low_steady",
        "execution_status": "SUCCESS",
        "solver_binary": "wsl:/usr/local/bin/lisflood",
        "solver_version": "LISFLOOD-FP version 8.0.3 (double)",
        "exit_code": 0,
        "runtime_seconds": 49.45388089999324,
        "stdout_tail": "***************************\n LISFLOOD-FP version 8.0.3 (double)\nRectangular channels only.\n_CALCULATE_Q_MODE 1.\n***************************\n\nloop time 35.000000\n",
        "stderr_tail": "",
        "par_file_sha256": "48a17c39c7dab07b75fc7937d7f3aea2bda48dda237351b34d597aad50c34c2f",
        "dem_sha256": "bc2177d6075b16ff06bd7e578eabadd3e64a405f6e8d3dfb3e0980369f961075",
        "roughness_sha256": "fde9415f6ed722be8911141599a7f7187063e14e19917a5029edc91a7947ce85",
        "forcing_sha256": "fe6297b6aa3b44325d257c75feff7dd74062c3ed591a39013d88f86953cd48ff",
        "output_files": [
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_01_low_steady\\results\\scenario_01_low_steady-0000.elev",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_01_low_steady\\results\\scenario_01_low_steady-0000.wd",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_01_low_steady\\results\\scenario_01_low_steady-0001.elev",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_01_low_steady\\results\\scenario_01_low_steady-0001.wd",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_01_low_steady\\results\\scenario_01_low_steady-0002.elev",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_01_low_steady\\results\\scenario_01_low_steady-0002.wd",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_01_low_steady\\results\\scenario_01_low_steady.dem",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_01_low_steady\\results\\scenario_01_low_steady.inittm",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_01_low_steady\\results\\scenario_01_low_steady.mass",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_01_low_steady\\results\\scenario_01_low_steady.max",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_01_low_steady\\results\\scenario_01_low_steady.maxtm",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_01_low_steady\\results\\scenario_01_low_steady.mxe",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_01_low_steady\\results\\scenario_01_low_steady.totaltm",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_01_low_steady\\results\\scenario_01_low_steady_simulated_depth.tif"
        ],
        "max_depth_m": 0.32199999690055847,
        "inundated_cells": 710,
        "physically_simulated": true,
        "calibrated": false,
        "smoke_run": true,
        "created_at": "2026-09-09T22:57:18.500938+00:00",
        "mean_wet_depth_m": 0.07289718091487885,
        "depth_raster_path": "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_01_low_steady\\results\\scenario_01_low_steady_simulated_depth.tif",
        "command": [
          "wsl",
          "-d",
          "Ubuntu",
          "--",
          "bash",
          "-c",
          "cd '/mnt/c/Users/sawan/OneDrive/Desktop/JALAI/jalrakshak-ml-starter/data/processed/flood/physics_outputs/phase11_corpus_v1/scenario_01_low_steady/work' && /usr/local/bin/lisflood 'scenario_01_low_steady.par'"
        ],
        "work_directory": "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_01_low_steady\\work",
        "consumed_forcing_sha256": "856083a888912fb7db5f6b8d4f531b20b30f1ceb88d8294766f93078c8ce028e",
        "consumed_dem_sha256": "a468e9da29596cf92e68be596ff808624fd9d893a973907919ebfe9eba197c40"
      },
      {
        "scenario_id": "scenario_02_mod_steady",
        "execution_status": "SUCCESS",
        "solver_binary": "wsl:/usr/local/bin/lisflood",
        "solver_version": "LISFLOOD-FP version 8.0.3 (double)",
        "exit_code": 0,
        "runtime_seconds": 38.96530090000306,
        "stdout_tail": "***************************\n LISFLOOD-FP version 8.0.3 (double)\nRectangular channels only.\n_CALCULATE_Q_MODE 1.\n***************************\n\nloop time 35.000000\n",
        "stderr_tail": "",
        "par_file_sha256": "cd3e8e7af0b6bcdbfa649171617e59c7e78b20e4880bf964ff4f444d4ad80927",
        "dem_sha256": "bc2177d6075b16ff06bd7e578eabadd3e64a405f6e8d3dfb3e0980369f961075",
        "roughness_sha256": "fde9415f6ed722be8911141599a7f7187063e14e19917a5029edc91a7947ce85",
        "forcing_sha256": "791a04d99241c5c94e8549aaf1286bf870f00407d2beb65dfcfeb5793edb5e29",
        "output_files": [
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_02_mod_steady\\results\\scenario_02_mod_steady-0000.elev",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_02_mod_steady\\results\\scenario_02_mod_steady-0000.wd",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_02_mod_steady\\results\\scenario_02_mod_steady-0001.elev",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_02_mod_steady\\results\\scenario_02_mod_steady-0001.wd",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_02_mod_steady\\results\\scenario_02_mod_steady-0002.elev",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_02_mod_steady\\results\\scenario_02_mod_steady-0002.wd",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_02_mod_steady\\results\\scenario_02_mod_steady.dem",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_02_mod_steady\\results\\scenario_02_mod_steady.inittm",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_02_mod_steady\\results\\scenario_02_mod_steady.mass",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_02_mod_steady\\results\\scenario_02_mod_steady.max",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_02_mod_steady\\results\\scenario_02_mod_steady.maxtm",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_02_mod_steady\\results\\scenario_02_mod_steady.mxe",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_02_mod_steady\\results\\scenario_02_mod_steady.totaltm",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_02_mod_steady\\results\\scenario_02_mod_steady_simulated_depth.tif"
        ],
        "max_depth_m": 1.128000020980835,
        "inundated_cells": 5713,
        "physically_simulated": true,
        "calibrated": false,
        "smoke_run": true,
        "created_at": "2026-09-09T22:58:08.480676+00:00",
        "mean_wet_depth_m": 0.09646666049957275,
        "depth_raster_path": "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_02_mod_steady\\results\\scenario_02_mod_steady_simulated_depth.tif",
        "command": [
          "wsl",
          "-d",
          "Ubuntu",
          "--",
          "bash",
          "-c",
          "cd '/mnt/c/Users/sawan/OneDrive/Desktop/JALAI/jalrakshak-ml-starter/data/processed/flood/physics_outputs/phase11_corpus_v1/scenario_02_mod_steady/work' && /usr/local/bin/lisflood 'scenario_02_mod_steady.par'"
        ],
        "work_directory": "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_02_mod_steady\\work",
        "consumed_forcing_sha256": "33e9096deadf1c9dc244107b8d1767bf9f8f0445a8b78cd059e13f9af5beb332",
        "consumed_dem_sha256": "a468e9da29596cf92e68be596ff808624fd9d893a973907919ebfe9eba197c40"
      },
      {
        "scenario_id": "scenario_03_high_steady",
        "execution_status": "SUCCESS",
        "solver_binary": "wsl:/usr/local/bin/lisflood",
        "solver_version": "LISFLOOD-FP version 8.0.3 (double)",
        "exit_code": 0,
        "runtime_seconds": 40.65182289999211,
        "stdout_tail": "***************************\n LISFLOOD-FP version 8.0.3 (double)\nRectangular channels only.\n_CALCULATE_Q_MODE 1.\n***************************\n\nloop time 38.000000\n",
        "stderr_tail": "",
        "par_file_sha256": "1f5ced39e0e01543c728f4596f0cc02c762b1175cdd6055cf373f75ce8630a1d",
        "dem_sha256": "bc2177d6075b16ff06bd7e578eabadd3e64a405f6e8d3dfb3e0980369f961075",
        "roughness_sha256": "fde9415f6ed722be8911141599a7f7187063e14e19917a5029edc91a7947ce85",
        "forcing_sha256": "ecbebfc17b253ab1df9d8cd81424ccb981ec5f03288517be116c635c7a7215d9",
        "output_files": [
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_03_high_steady\\results\\scenario_03_high_steady-0000.elev",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_03_high_steady\\results\\scenario_03_high_steady-0000.wd",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_03_high_steady\\results\\scenario_03_high_steady-0001.elev",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_03_high_steady\\results\\scenario_03_high_steady-0001.wd",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_03_high_steady\\results\\scenario_03_high_steady-0002.elev",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_03_high_steady\\results\\scenario_03_high_steady-0002.wd",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_03_high_steady\\results\\scenario_03_high_steady.dem",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_03_high_steady\\results\\scenario_03_high_steady.inittm",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_03_high_steady\\results\\scenario_03_high_steady.mass",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_03_high_steady\\results\\scenario_03_high_steady.max",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_03_high_steady\\results\\scenario_03_high_steady.maxtm",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_03_high_steady\\results\\scenario_03_high_steady.mxe",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_03_high_steady\\results\\scenario_03_high_steady.totaltm",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_03_high_steady\\results\\scenario_03_high_steady_simulated_depth.tif"
        ],
        "max_depth_m": 2.263000011444092,
        "inundated_cells": 22402,
        "physically_simulated": true,
        "calibrated": false,
        "smoke_run": true,
        "created_at": "2026-09-09T22:58:47.926254+00:00",
        "mean_wet_depth_m": 0.09238091111183167,
        "depth_raster_path": "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_03_high_steady\\results\\scenario_03_high_steady_simulated_depth.tif",
        "command": [
          "wsl",
          "-d",
          "Ubuntu",
          "--",
          "bash",
          "-c",
          "cd '/mnt/c/Users/sawan/OneDrive/Desktop/JALAI/jalrakshak-ml-starter/data/processed/flood/physics_outputs/phase11_corpus_v1/scenario_03_high_steady/work' && /usr/local/bin/lisflood 'scenario_03_high_steady.par'"
        ],
        "work_directory": "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_03_high_steady\\work",
        "consumed_forcing_sha256": "36af66d26e585367c67917e0cd0bea53f07151505cd1e1cc5dfc8a58f1ec1ada",
        "consumed_dem_sha256": "a468e9da29596cf92e68be596ff808624fd9d893a973907919ebfe9eba197c40"
      },
      {
        "scenario_id": "scenario_04_front_loaded",
        "execution_status": "SUCCESS",
        "solver_binary": "wsl:/usr/local/bin/lisflood",
        "solver_version": "LISFLOOD-FP version 8.0.3 (double)",
        "exit_code": 0,
        "runtime_seconds": 54.341454099994735,
        "stdout_tail": "***************************\n LISFLOOD-FP version 8.0.3 (double)\nRectangular channels only.\n_CALCULATE_Q_MODE 1.\n***************************\n\nloop time 49.000000\n",
        "stderr_tail": "",
        "par_file_sha256": "7a87e25ad32ae9a83e007156297f6912c411b68e05242d1fcdd2578fd8ef4e56",
        "dem_sha256": "bc2177d6075b16ff06bd7e578eabadd3e64a405f6e8d3dfb3e0980369f961075",
        "roughness_sha256": "fde9415f6ed722be8911141599a7f7187063e14e19917a5029edc91a7947ce85",
        "forcing_sha256": "c41c35d1766cef4f3dcc57215858bb65ae7153d19f7205a47302f0dfc82dfa5e",
        "output_files": [
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_04_front_loaded\\results\\scenario_04_front_loaded-0000.elev",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_04_front_loaded\\results\\scenario_04_front_loaded-0000.wd",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_04_front_loaded\\results\\scenario_04_front_loaded-0001.elev",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_04_front_loaded\\results\\scenario_04_front_loaded-0001.wd",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_04_front_loaded\\results\\scenario_04_front_loaded-0002.elev",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_04_front_loaded\\results\\scenario_04_front_loaded-0002.wd",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_04_front_loaded\\results\\scenario_04_front_loaded.dem",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_04_front_loaded\\results\\scenario_04_front_loaded.inittm",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_04_front_loaded\\results\\scenario_04_front_loaded.mass",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_04_front_loaded\\results\\scenario_04_front_loaded.max",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_04_front_loaded\\results\\scenario_04_front_loaded.maxtm",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_04_front_loaded\\results\\scenario_04_front_loaded.mxe",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_04_front_loaded\\results\\scenario_04_front_loaded.totaltm",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_04_front_loaded\\results\\scenario_04_front_loaded_simulated_depth.tif"
        ],
        "max_depth_m": 2.628999948501587,
        "inundated_cells": 21401,
        "physically_simulated": true,
        "calibrated": false,
        "smoke_run": true,
        "created_at": "2026-09-09T22:59:29.106561+00:00",
        "mean_wet_depth_m": 0.084957055747509,
        "depth_raster_path": "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_04_front_loaded\\results\\scenario_04_front_loaded_simulated_depth.tif",
        "command": [
          "wsl",
          "-d",
          "Ubuntu",
          "--",
          "bash",
          "-c",
          "cd '/mnt/c/Users/sawan/OneDrive/Desktop/JALAI/jalrakshak-ml-starter/data/processed/flood/physics_outputs/phase11_corpus_v1/scenario_04_front_loaded/work' && /usr/local/bin/lisflood 'scenario_04_front_loaded.par'"
        ],
        "work_directory": "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_04_front_loaded\\work",
        "consumed_forcing_sha256": "65464d51727954ea60f13b286283e564586ddf64caf25e9ff516679d726f2513",
        "consumed_dem_sha256": "a468e9da29596cf92e68be596ff808624fd9d893a973907919ebfe9eba197c40"
      },
      {
        "scenario_id": "scenario_05_back_loaded",
        "execution_status": "SUCCESS",
        "solver_binary": "wsl:/usr/local/bin/lisflood",
        "solver_version": "LISFLOOD-FP version 8.0.3 (double)",
        "exit_code": 0,
        "runtime_seconds": 61.51798340000096,
        "stdout_tail": "***************************\n LISFLOOD-FP version 8.0.3 (double)\nRectangular channels only.\n_CALCULATE_Q_MODE 1.\n***************************\n\nloop time 59.000000\n",
        "stderr_tail": "",
        "par_file_sha256": "cc7d5f24260e3435a1d21b1224ef9ebad8ade94e3ee5743bc7a2b629d54f955c",
        "dem_sha256": "bc2177d6075b16ff06bd7e578eabadd3e64a405f6e8d3dfb3e0980369f961075",
        "roughness_sha256": "fde9415f6ed722be8911141599a7f7187063e14e19917a5029edc91a7947ce85",
        "forcing_sha256": "27ffb5ebf4c0e78eab266fba4c8d7a8c9fa9a83d4c176b8f82c07c432ba9a88f",
        "output_files": [
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_05_back_loaded\\results\\scenario_05_back_loaded-0000.elev",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_05_back_loaded\\results\\scenario_05_back_loaded-0000.wd",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_05_back_loaded\\results\\scenario_05_back_loaded-0001.elev",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_05_back_loaded\\results\\scenario_05_back_loaded-0001.wd",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_05_back_loaded\\results\\scenario_05_back_loaded-0002.elev",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_05_back_loaded\\results\\scenario_05_back_loaded-0002.wd",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_05_back_loaded\\results\\scenario_05_back_loaded.dem",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_05_back_loaded\\results\\scenario_05_back_loaded.inittm",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_05_back_loaded\\results\\scenario_05_back_loaded.mass",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_05_back_loaded\\results\\scenario_05_back_loaded.max",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_05_back_loaded\\results\\scenario_05_back_loaded.maxtm",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_05_back_loaded\\results\\scenario_05_back_loaded.mxe",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_05_back_loaded\\results\\scenario_05_back_loaded.totaltm",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_05_back_loaded\\results\\scenario_05_back_loaded_simulated_depth.tif"
        ],
        "max_depth_m": 1.399999976158142,
        "inundated_cells": 22210,
        "physically_simulated": true,
        "calibrated": false,
        "smoke_run": true,
        "created_at": "2026-09-09T23:00:27.668663+00:00",
        "mean_wet_depth_m": 0.07210864126682281,
        "depth_raster_path": "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_05_back_loaded\\results\\scenario_05_back_loaded_simulated_depth.tif",
        "command": [
          "wsl",
          "-d",
          "Ubuntu",
          "--",
          "bash",
          "-c",
          "cd '/mnt/c/Users/sawan/OneDrive/Desktop/JALAI/jalrakshak-ml-starter/data/processed/flood/physics_outputs/phase11_corpus_v1/scenario_05_back_loaded/work' && /usr/local/bin/lisflood 'scenario_05_back_loaded.par'"
        ],
        "work_directory": "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_05_back_loaded\\work",
        "consumed_forcing_sha256": "7271b1f2fab857f576dae90b696c7b7c04c12dd34d4681ecf0a8be136833c006",
        "consumed_dem_sha256": "a468e9da29596cf92e68be596ff808624fd9d893a973907919ebfe9eba197c40"
      },
      {
        "scenario_id": "scenario_06_short_intense",
        "execution_status": "SUCCESS",
        "solver_binary": "wsl:/usr/local/bin/lisflood",
        "solver_version": "LISFLOOD-FP version 8.0.3 (double)",
        "exit_code": 0,
        "runtime_seconds": 29.640824999994948,
        "stdout_tail": "***************************\n LISFLOOD-FP version 8.0.3 (double)\nRectangular channels only.\n_CALCULATE_Q_MODE 1.\n***************************\n\nloop time 27.000000\n",
        "stderr_tail": "",
        "par_file_sha256": "a7be8865b946029c0923085058a3446b8dce5ac16fdb002a45f7eca1ecd5e704",
        "dem_sha256": "bc2177d6075b16ff06bd7e578eabadd3e64a405f6e8d3dfb3e0980369f961075",
        "roughness_sha256": "fde9415f6ed722be8911141599a7f7187063e14e19917a5029edc91a7947ce85",
        "forcing_sha256": "db3da5978c81494d2dde874976b435e0ea6ebd04cad3d9705222a35ae9adf33a",
        "output_files": [
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_06_short_intense\\results\\scenario_06_short_intense-0000.elev",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_06_short_intense\\results\\scenario_06_short_intense-0000.wd",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_06_short_intense\\results\\scenario_06_short_intense-0001.elev",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_06_short_intense\\results\\scenario_06_short_intense-0001.wd",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_06_short_intense\\results\\scenario_06_short_intense-0002.elev",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_06_short_intense\\results\\scenario_06_short_intense-0002.wd",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_06_short_intense\\results\\scenario_06_short_intense.dem",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_06_short_intense\\results\\scenario_06_short_intense.inittm",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_06_short_intense\\results\\scenario_06_short_intense.mass",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_06_short_intense\\results\\scenario_06_short_intense.max",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_06_short_intense\\results\\scenario_06_short_intense.maxtm",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_06_short_intense\\results\\scenario_06_short_intense.mxe",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_06_short_intense\\results\\scenario_06_short_intense.totaltm",
          "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_06_short_intense\\results\\scenario_06_short_intense_simulated_depth.tif"
        ],
        "max_depth_m": 3.318000078201294,
        "inundated_cells": 23155,
        "physically_simulated": true,
        "calibrated": false,
        "smoke_run": true,
        "created_at": "2026-09-09T23:01:30.042181+00:00",
        "mean_wet_depth_m": 0.10747402161359787,
        "depth_raster_path": "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_06_short_intense\\results\\scenario_06_short_intense_simulated_depth.tif",
        "command": [
          "wsl",
          "-d",
          "Ubuntu",
          "--",
          "bash",
          "-c",
          "cd '/mnt/c/Users/sawan/OneDrive/Desktop/JALAI/jalrakshak-ml-starter/data/processed/flood/physics_outputs/phase11_corpus_v1/scenario_06_short_intense/work' && /usr/local/bin/lisflood 'scenario_06_short_intense.par'"
        ],
        "work_directory": "C:\\Users\\sawan\\OneDrive\\Desktop\\JALAI\\jalrakshak-ml-starter\\data\\processed\\flood\\physics_outputs\\phase11_corpus_v1\\scenario_06_short_intense\\work",
        "consumed_forcing_sha256": "9f88be9d09f0b47a0b418a72285a40a93fbb3594d887ad09d0748bb96221331b",
        "consumed_dem_sha256": "a468e9da29596cf92e68be596ff808624fd9d893a973907919ebfe9eba197c40"
      }
    ],
    "dataset_version": "phase11_square_smoke_v1",
    "verified": true,
    "normalization_train_only_verified": true,
    "training_eligibility": "SMOKE_ONLY_ONE_60MIN_TARGET; independent of legacy checkpoint"
  },
  "manual_reference": "https://www.bristol.ac.uk/media-library/sites/geography/migrated/documents/lisflood-manual-v5.9.6.pdf"
}
```
