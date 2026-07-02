"""
Direct XPlatform data fetcher — replays captured requests and parses
the XPlatform proprietary binary response format (application/octet-stream).

XPlatform binary protocol (reverse-engineered):
  - Response starts with ff ad (magic), followed by zlib-compressed data
  - Decompressed data contains one or more fe 10 blocks (datasets)
  - Each block has a header, column definitions, and row data
  - Row values use typed encoding: null, string, int32, float64, bool

Run capture first:  python proxy_intercept.py
Then run forever:   python main.py
"""

import json
import os
import re
import struct
import zlib
import calendar
import logging
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

MANILA_TZ = timezone(timedelta(hours=8))

REQUESTS_FILE = os.path.join(os.path.dirname(__file__), "xp_requests.json")
MES_URL = os.getenv("MES_URL", "http://107.105.195.34:8080")
MES_USERNAME = os.getenv("MES_USERNAME", "")
MES_PASSWORD = os.getenv("MES_PASSWORD", "")

# ── RPT40281 WIP Status: binary di-code → human-readable column name ─────────
# Derived by comparing binary values against RPT40281.xlsx column headers.
# Unmapped di-codes are stored as-is (raw di-code name).
# ── RPT40281 WIP Status: binary di-code → human-readable column name ─────────
# Verified by matching binary row values against RPT40281.txt (Excel export).
# Binary col order confirmed from debug_rpt_capture_0.bin header extraction.
WIP_COL_MAP: dict[str, str] = {
    # [0]  _chk stays as _chk
    # [1]  di00002178  = FP PLAN
    "di00002178":      "fp_plan",
    # [2]  di00000256  = Major process name
    "di00000256":      "major_process_name",
    # [3]  di00001901  = Facility
    "di00001901":      "facility",
    # [4]  di00001699  = Middle Step Name
    "di00001699":      "middle_step_name",
    # [5]  current_qty_sum = row sequence (internal, not mapped)
    # [6]  di00000258  = Process Name
    "di00000258":      "process_name",
    # [7]  di00002635  = Status
    "di00002635":      "status",
    # [8]  di00000304  = Powder LOT
    "di00000304":      "powder_lot",
    # [9]  di00000305  = Batch LOT
    "di00000305":      "batch_lot",
    # [10] di00000308  = Print LOT
    "di00000308":      "print_lot",
    # [11] di00001122  = Stacking LOT
    "di00001122":      "stacking_lot",
    # [12] di00008859  = Stacking Finish Equipment
    "di00008859":      "stacking_finish_equip",
    # [13] di00000262  = LOT No.
    "di00000262":      "lot_no",
    # [14] di00000265  = Model ID
    "di00000265":      "model_id",
    # [15] di00006439  = LOT production process
    "di00006439":      "lot_production_process",
    # [16] di00000653  = Powder type
    "di00000653":      "powder_type",
    # [17] di00000574  = Composition
    "di00000574":      "composition",
    # [18] di00001256  = Whether precision trimming is applied
    "di00001256":      "whether_precision_trimming",
    # [19] di00000734  = Casting Type
    "di00000734":      "casting_type",
    # [20] di00001060  = Size
    "di00001060":      "size",
    # [21] di00000365  = Cp.Type
    "di00000365":      "cp_type",
    # [22] di00004069  = Automotive YN
    "di00004069":      "automotive_yn",
    # [23] di00006759  = Product type
    "di00006759":      "product_type",
    # [24] di00004007  = MODEL(13)
    "di00004007":      "model_13",
    # [25] di00001062  = MODEL(6)
    "di00001062":      "model_6",
    # [26] di00003158  = Carrier Plate ID
    "di00003158":      "carrier_plate_id",
    # [27] di00001918  = External Termination paste name (slot2 always empty)
    "di00001918":      "ext_term_paste",
    # [28] di00004638  = Consumable Model1
    "di00004638":      "consumable_model1",
    # [29] di00004639  = Consumable Model2
    "di00004639":      "consumable_model2",
    # [30] di00004640  = Consumable Model3
    "di00004640":      "consumable_model3",
    # [31] di00004641  = Consumable Model4
    "di00004641":      "consumable_model4",
    # [32] di00000494  = First input Qty
    "di00000494":      "first_input_qty",
    # [33] di00000294  = Current Qty
    "di00000294":      "current_qty",
    # [34] di00001058  = Lamination BAR Q'ty
    "di00001058":      "lamination_bar_qty",
    # [35] di00001059  = Cutting BAR Qty
    "di00001059":      "cutting_bar_qty",
    # [36] di00000369  = LOT Type
    "di00000369":      "lot_type",
    # [37] di00000370  = LOT Details
    "di00000370":      "lot_details",
    # [38] di00006279  = Corporation First Chip LOT
    "di00006279":      "corp_first_chip_lot",
    # [39] di00010259  = GLOBAL First Chip LOT
    "di00010259":      "global_first_chip_lot",
    # [40] di00010520  = GLOBAL First Chip Model
    "di00010520":      "global_first_chip_model",
    # [41] di00000652  = Pre LOT
    "di00000652":      "pre_lot",
    # [42] di00003618  = Prev. major process finish date
    "di00003618":      "prev_major_process_finish_date",
    # [43] di00001121  = Major process elapsed days
    "di00001121":      "major_process_elapsed_days",
    # [44] di00006499  = Buffer Elapse Date
    "di00006499":      "buffer_elapse_date",
    # [45] di00006500  = Major process elapsed days - Buffer Elapse Date
    "di00006500":      "major_process_elapsed_minus_buffer",
    # [46] di00003465  = Date and time
    "di00003465":      "date_and_time",
    # [47] di00003466  = Major-process Recieve Elapse Date
    "di00003466":      "major_process_recieve_elapse_date",
    # [48] di00000374  = Prev. process finish date
    "di00000374":      "prev_process_finish_date",
    # [49] di00000729  = Process elapsed days
    "di00000729":      "process_elapsed_days",
    # [50] di00001118  = Firing time
    "di00001118":      "firing_time",
    # [51] di00001420  = Lot Through time
    "di00001420":      "lot_through_time",
    # [52] di00000273  = Input datetime
    "di00000273":      "input_datetime",
    # [53] di00001920  = Equipment Input datetime
    "di00001920":      "equip_input_datetime",
    # [54] di00001419  = Actual input date and time
    "di00001419":      "actual_input_datetime",
    # [55] di00001119  = Estimated completion time
    "di00001119":      "estimated_completion_time",
    # [56] di00000297  = Urgency
    "di00000297":      "urgency",
    # [57] di00008999  = emergency changer
    "di00008999":      "emergency_changer",
    # [58] di00001240  = Work Facility
    "di00001240":      "work_facility",
    # [59] di00001854  = Work Equip.
    "di00001854":      "work_equip",
    # [60] di00002335  = Rack
    "di00002335":      "rack",
    # [61] di00002825  = BIN
    "di00002825":      "bin",
    # [62] di00001125  = LOT Card
    "di00001125":      "lot_card",
    # [63] di00000277  = Derive Y/N
    "di00000277":      "derive_yn",
    # [64] di00000264  = Derive Cause
    "di00000264":      "derive_cause",
    # [65] di00009779  = Termination routing name
    "di00009779":      "termination_routing_name",
    # [66] di00009780  = Insp. Type
    "di00009780":      "insp_type",
    # [67] di00000298  = Nonconformity Y/N
    "di00000298":      "nonconformity_yn",
    # [68] di00000299  = Whether COQ
    "di00000299":      "whether_coq",
    # [69] di00000278  = ISRework
    "di00000278":      "is_rework",
    # [70] di00000280  = Rework type
    "di00000280":      "rework_type",
    # [71] di00000281  = LOT generation type
    "di00000281":      "lot_generation_type",
    # [72] di00000283  = Customer
    "di00000283":      "customer",
    # [73] di00000661  = Customer Name
    "di00000661":      "customer_name",
    # [74] di00000284  = Remarks
    "di00000284":      "remarks",
    # [75] di00000290  = Warehouse re-work YN
    "di00000290":      "warehouse_rework_yn",
    # [76] di00000291  = Warehouse rework order number
    "di00000291":      "warehouse_rework_order_no",
    # [77] di00000446  = CHIP type
    "di00000446":      "chip_type",
    # [78] di00004559  = 1st Firing profile
    "di00004559":      "first_firing_profile",
    # [79] di00000289  = Firing profile
    "di00000289":      "firing_profile",
    # [80] di00004560  = 1st Re-Oxidation profile
    "di00004560":      "first_reoxidation_profile",
    # [81] di00004561  = 2nd Re-Oxidation profile
    "di00004561":      "second_reoxidation_profile",
    # [82] di00005899  = 1st Bake profile
    "di00005899":      "first_bake_profile",
    # [83] di00005900  = 2st Bake profile
    "di00005900":      "second_bake_profile",
    # [84] di00003854  = Model change reservation Y/N
    "di00003854":      "model_change_reservation_yn",
    # [85] di00001298  = Barrel Qty
    "di00001298":      "barrel_qty",
    # [86] di00001257  = Box Qty (verified: 2 matches txt [85])
    "di00001257":      "box_qty",
    # [87] di00002298  = LOT weight (g) (verified: 7055 matches txt [86])
    "di00002298":      "lot_weight_g",
    # [88] di00001700  = Load (verified: FF230X230 matches txt [87] Load)
    "di00001700":      "load",
    # [90] di00002184  = (unnamed col, internal)
    "di00002184":      "loading_stages",
    # [93] di00002185  = (unnamed col, internal)
    "di00002185":      "stone_label_internal",
    # [94] di00001163  = Stone Label (verified: empty matches txt [94] Stone Label)
    "di00001163":      "stone_label",
    # [95] di00001166  = (unnamed/empty col between stone_label and powder_sap_model)
    "di00001166":      "powder_sap_model_raw",
    # [96] di00000285  = Powder SAP model (verified: MJ96-00003J matches txt [95])
    "di00000285":      "powder_sap_model",
    # [97] di00001061  = Powder SAP model name (verified: ASSY PW;C,R,CSZT-M7 matches txt [96])
    "di00001061":      "powder_sap_model_name",
    # [98] di00001064  = Powder Size (verified: 400 matches txt [97])
    "di00001064":      "powder_size",
    # [99] di00000568  = Batch SAP Model (verified: MJ96-06003Q matches txt [98])
    "di00000568":      "batch_sap_model",
    # [100] di00000306 = Batch creation date (verified: 2024-08-16 03:05 matches txt [99])
    "di00000306":      "batch_creation_date",
    # [101] di00004058 = Batch Elapsed input date (verified: 582.35 matches txt [100])
    "di00004058":      "batch_elapsed_input_date",
    # [102] di00001618 = Aging Rate (verified: empty matches txt [101])
    "di00001618":      "aging_rate",
    # [103] di00002918 = Aging Rate (Y/N) (verified: Y matches txt [102])
    "di00002918":      "aging_rate_yn",
    # [104] di00001123 = Stacking Date (verified: 2024-11-07 03:56 matches txt [103])
    "di00001123":      "stacking_date",
    # [105] di00001124 = Stacking create elapsed days (verified: 499.31 matches txt [104])
    "di00001124":      "stacking_create_elapsed_days",
    # [106] di00003859 = Current Proc. profile (verified: empty matches txt [105])
    "di00003859":      "current_proc_profile",
    # [107] di00003869 = Stacking finished date (verified: 2024-11-09 01:29 matches txt [106])
    "di00003869":      "stacking_finished_date",
    # [108] di00000449 = Design Layer (verified: 27L10B matches txt [107])
    "di00000449":      "design_layer",
    # [109] di00000309 = PrintModel (verified: SC3600C6C... matches txt [108])
    "di00000309":      "print_model",
    # [110] di00004068 = Screen Type (verified: SCREEN matches txt [109])
    "di00004068":      "screen_type",
    # [111] di00000288 = Screen Model (verified: D10CMSI46-NOR-SA02IC matches txt [110])
    "di00000288":      "screen_model",
    # [112] di00002361 = Stacking Equip. Group (verified: empty matches txt [111])
    "di00002361":      "stacking_equip_group",
    # [113] di00006280 = First CHIP Model (verified: CL10C221JC81PBB matches txt [112])
    "di00006280":      "first_chip_model",
    # [114] di00006459 = Prev. CHIP Model (verified: CL10C221JC81PBB matches txt [113])
    "di00006459":      "prev_chip_model",
    # [115] di00000292 = CHIP/BAR Qty (verified: 14410 matches txt [114])
    "di00000292":      "chip_bar_qty",
    # [116] di00000310 = Inner Paste Model (verified: 1NICS(NCS11) matches txt [115])
    "di00000310":      "inner_paste_model",
    # [117] di00000286 = Week (verified: 202445 matches txt [116])
    "di00000286":      "week",
    # [118] di00000311 = Prev. Product (verified: CL10C221JC81PBB matches txt [117])
    "di00000311":      "prev_product",
    # [119] di00000312 = Expt. in-charge (verified: username matches txt [118])
    "di00000312":      "expt_incharge",
    # [120] di00000313 = Expt. Remarks (verified: matches txt [119])
    "di00000313":      "expt_remarks",
    # [121] di00000314 = Hold (Y/N) (verified: N matches txt [120])
    "di00000314":      "hold_yn",
    # [122] di00000317 = Hold Count (verified: matches txt [121])
    "di00000317":      "hold_count",
    # [123] di00000318 = HoldWorker (verified: matches txt [122])
    "di00000318":      "hold_worker",
    # [124] di00000320 = HoldDate (verified: matches txt [123])
    "di00000320":      "hold_date",
    # [125] di00000624 = Hold Type (verified: matches txt [124])
    "di00000624":      "hold_type",
    # [126] di00002367 = Hold Time (verified: matches txt [125])
    "di00002367":      "hold_time",
    # [127] di00004920 = Hold Detail Code (verified: matches txt [126])
    "di00004920":      "hold_detail_code",
    # [128] di00000315 = Hold Code (verified: matches txt [127])
    "di00000315":      "hold_code",
    # [129] di00001538 = Holder (verified: matches txt [128])
    "di00001538":      "holder",
    # [130] di00000348 = Hold action steps (verified: matches txt [129])
    "di00000348":      "hold_action_steps",
    # [131] di00005879 = First Hold Date (verified: matches txt [130])
    "di00005879":      "first_hold_date",
    # [132] di00000316 = Hold Reason (verified: matches txt [131])
    "di00000316":      "hold_reason",
    # [133] di00000321 = Treatment Remark (verified: matches txt [132])
    "di00000321":      "treatment_remark",
    # [134] di00000319 = Reserve Incharge (verified: matches txt [133])
    "di00000319":      "reserve_incharge",
    # [135] di00000322 = PM (verified: SUMAGUE, FHIRLLY MARIE CORONADO matches txt [134])
    "di00000322":      "pm",
    # [136] di00000323 = Action 1 (txt [135])
    "di00000323":      "action1",
    # [137] di00000324 = Action 2 (txt [136])
    "di00000324":      "action2",
    # [138] di00000326 = Determining progress (txt [137])
    "di00000326":      "determining_progress",
    # [139] di00000325 = Release Reason (txt [138])
    "di00000325":      "release_reason",
    # [140] di00002878 = DC 8001 Creator (verified: username matches txt [139] DC 8001 Creator)
    "di00002878":      "dc8001_creator",
    # [139] di00003931 = OI Qty check time (verified: datetime matches txt [140] OI Qty check time)
    "di00003931":      "oi_qty_check_time",
    # [140] di00004009 = Cutting size Inspection (verified: matches txt [141])
    "di00004009":      "cutting_size_inspection",
    # [141] di00004010 = Firing inspection (verified: matches txt [142])
    "di00004010":      "firing_inspection",
    # [142] di00004011 = Tumbling C/DF Insp. (verified: matches txt [143])
    "di00004011":      "tumbling_cdf_insp",
    # [143] di00004012 = Tumbling BDV Insp. (verified: matches txt [144])
    "di00004012":      "tumbling_bdv_insp",
    # [144] di00004013 = Final TF C/DF Inspt. (verified: NG matches txt [145])
    "di00004013":      "final_tf_cdf_insp",
    # [145] di00004014 = Term. proj/densification insp. (verified: matches txt [146])
    "di00004014":      "term_proj_densification_insp",
    # [146] di00000897 = Plating test (verified: matches txt [147])
    "di00000897":      "plating_test",
    # [147] di00004015 = Reliability Inspection (verified: matches txt [148])
    "di00004015":      "reliability_insp",
    # [148] di00006719 = (Premass) Final TF C/DF Inspt. (verified: '00' matches txt [149])
    "di00006719":      "premass_final_tf_cdf_insp",
    # [149] di00007339 = The final step (verified: 'Outgoing Inspection' matches txt [150])
    "di00007339":      "final_step",
    # [150] di00007359 = LOT Finish Date (verified: date matches txt [151])
    "di00007359":      "lot_finish_date",
    # [151] di00000349 = OutGoing type (txt [152] OutGoing)
    "di00000349":      "outgoing_type",
    # [152] di00000350 = OutGoing date (txt [153])
    "di00000350":      "outgoing_date",
    # [153] di00000351 = MCS (verified: 'C' matches txt [154] MCS)
    "di00000351":      "mcs",
    # [154-157] di00000352-354 = screen pattern cols (txt [155-157])
    "di00000352":      "screen_pattern_1",
    "di00000353":      "screen_pattern_2",
    "di00000354":      "screen_pattern_3",
    # [158] di00000561 = Screen Pattern (verified: '4' matches txt [158] Screen Pattern)
    "di00000561":      "screen_pattern_4",
    # [159] di00000827 = Screenshot head value (verified: '4' matches txt [159])
    "di00000827":      "screenshot_head_value",
    # [160] di00001978 = Stacking BAR Size (verified: '330mm' matches txt [160])
    "di00001978":      "stacking_bar_size",
    # [161] di00001979 = Cutting BAR size type (verified: '170*170' matches txt [161])
    "di00001979":      "cutting_bar_size_type",
    # [162] di00002058 = (unmapped — empty in binary)

    # [164] di00000247 = Generation model group
    "di00000247":      "generation_model_group",
    # [165] di00006039 = Model Level
    "di00006039":      "model_level",
    # [166] di00002898 = Verification Type
    "di00002898":      "verification_type",
    # [167] di00002899 = DF Spec
    "di00002899":      "df_spec",
    # [168] di00004008 = Termination BDV Spec
    "di00004008":      "termination_bdv_spec",
    # [169] di00003159 = Reservation hold status
    "di00003159":      "reservation_hold_status",
    # [170] di00003160 = Reservation Reason
    "di00003160":      "reservation_reason",
    # [171] di00003218 = Visual 4 sides 6 facilities
    "di00003218":      "visual_4sides_6facilities",
    # [172] di00003219 = Visual TWA equipment
    "di00003219":      "visual_twa_equipment",
    # [173-180] Equip 1-8 / mesh info
    "di00001224":      "equip_1",
    "di00001225":      "equip_2",
    "di00001226":      "equip_3",
    "di00001558":      "equip_4",
    "di00002290":      "equip_6",
    "di00002291":      "current_process_mesh_type",
    "di00002292":      "current_process_mesh_size",
    "di00002293":      "current_process_mesh_qty",
    # [181] di00000266 = Routing
    "di00000266":      "routing",
    # [182] di00003748 = RoutingName
    "di00003748":      "routing_name",
    # [183] di00003870 = Stacking finish elapsed days
    "di00003870":      "stacking_finish_elapsed_days",
    # [184] di00003932 = DC8001 LockingYN
    "di00003932":      "dc8001_locking_yn",
    # [185] di00005387 = DC8001 Release Y/N
    "di00005387":      "dc8001_release_yn",
    # [186] di00005388 = COQ Status
    "di00005388":      "coq_status",
    # [187] di00006019 = SGMLIMIT0004 Limit Status
    "di00006019":      "sgmlimit0004_status",
    # [188] di00006020 = SGMLIMIT0010 Limit Status
    "di00006020":      "sgmlimit0010_status",
    # [189] di00005303 = Firing Chip Buffer L/T
    "di00005303":      "firing_chip_buffer_lt",
    # [190] di00005621 = REP. Model Automotive electronics Type
    "di00005621":      "rep_model_automotive_type",
    # [191] di00005599 = LIPAS WIP
    "di00005599":      "lipas_wip",
    # [192] di00005640 = SAP Experiment ID
    "di00005640":      "sap_experiment_id",
    # [193] di00005641 = GPLM Document No
    "di00005641":      "gplm_document_no",
    # [194] di00005780 = Cover Batch LOT
    "di00005780":      "cover_batch_lot",
    # [195] di00005781 = Cover Roll LOT
    "di00005781":      "cover_roll_lot",
    # [196] di00000434 = Cover design thickness
    "di00000434":      "cover_design_thickness",
    # [197] di00000432 = Top cover Layer
    "di00000432":      "top_cover_layer",
    # [198] di00000433 = Bottom Cover Layer
    "di00000433":      "bottom_cover_layer",
    # [199] di00005740 = Cover Batch code
    "di00005740":      "cover_batch_code",
    # [200] di00006099 = PRODUCTION TEAM TYPE
    "di00006099":      "production_team_type",
    # [201] di00000421 = Paste LOT
    "di00000421":      "paste_lot",
    # [202] di00009179 = Major process/process L/T progress Y/N
    "di00009179":      "major_process_lt_progress_yn",
    # [203] di00007000 = District
    "di00007000":      "district",
    # [204] di00007259 = Mater Information Registration Y/N
    "di00007259":      "mater_info_registration_yn",
    # [205] di00000429 = Active Layer
    "di00000429":      "active_layer",
    # [206] di00000415 = Carrier ID
    "di00000415":      "carrier_id",
    # [207] di00006486 = Estimated Finish Time
    "di00006486":      "estimated_finish_time",
    # [208] di00007579 = Real WIP Qty
    "di00007579":      "real_wip_qty",
    # [209] di00007660 = Carrier Qty
    "di00007660":      "carrier_qty",
    # [210] di00001128 = Pattern Area
    "di00001128":      "pattern_area",
    # [211] di00005659 = Total Area
    "di00005659":      "total_area",
    # [212] di00007719 = 1st Firing Finish~Main Firing Input(Hrs)
    "di00007719":      "first_firing_to_main_firing_hrs",
    # [213] di00007720 = 2nd BO Finish~Main Firing Input(Hrs)
    "di00007720":      "second_bo_to_main_firing_hrs",
    # [214] di00008139 = Temporary work guide file number
    "di00008139":      "temp_work_guide_file_no",
    # [215] di00004802 = Dry Hard profile
    "di00004802":      "dry_hard_profile",
    # [216] di00009999 = Top LOT
    "di00009999":      "top_lot",
    # [217] di00010000 = Checking Good Vinyl WorkDate
    "di00010000":      "checking_good_vinyl_workdate",
    # [218] di00010001 = Checking Good Viny Operator
    "di00010001":      "checking_good_vinyl_operator",
    # [219] di00005984 = Special code
    "di00005984":      "special_code",
    # [220] di00010579 = 1st Term. firing profile
    "di00010579":      "first_term_firing_profile",
    # [221] di00010580 = 2st Term. firing profile
    "di00010580":      "second_term_firing_profile",
    # [222] di00010581 = 3st Term. firing profile
    "di00010581":      "third_term_firing_profile",
    # [223] di00010582 = Final Term. firing profile
    "di00010582":      "final_term_firing_profile",
    # [224] di00010599 = Ring usage compared to quantity
    "di00010599":      "ring_usage_vs_qty",
}


# ── RPT40496 Monthly Compliance: actual binary column names ──────────────────
# Extracted from live binary response (response_text_sample in xp_requests.json)
# a0_v..a9_v are dynamic WIP process breakdown columns (count given by colnum)
MONTHLY_COLS = [
    "_chk", "site_div_seq", "prod_type", "site_name", "prod_id",
    "input_prod_id", "plan_d_day", "locking_yn",
    "plan_qty", "plan_qty_d7", "plan_qty_d9", "plan_qty_d0",
    "goc_uld_yield", "global_plan_qty", "mplan_qty",
    "end_qty", "end_qty_d0",
    "inplan_qty", "inplan_qty_d7", "inplan_qty_d9",
    "inplan_endrate", "inplan_endrate_d7", "inplan_endrate_d9",
    "endrate", "endrate_d0",
    "diff_qty", "lack_qty", "lack_qty_d7", "lack_qty_d9", "lack_qty_d0",
    "yidid_d5", "yidid_d7", "yidid_d9",
    "minplan_qty", "minplan_endrate", "mendrate",
    "colnum", "wip_qty", "avr_lt",
    "a0_v", "a1_v", "a2_v", "a3_v", "a4_v",
    "a5_v", "a6_v", "a7_v", "a8_v", "a9_v",
]

# Map binary column names → DB column names for monthly_plan table.
# Verified by matching raw binary values against RPT40496.xlsx row CL03A104KA3NNPB:
#   Excel: volpas=1194, lipas_g=21803, lipas_d5=21803, result=20614,
#          result_ratio=94.55, plan_result_d5=20614, plan_ratio_d5=94.50,
#          excess=-1189, lack_d5=1189, goc_yield=92.81, lack_yield=1281,
#          wip_total=6881, tat=42.8
MONTHLY_COL_MAP = {
    # identity — confirmed
    "site_div_seq":       "site_code",        # 'E502AAPG04'
    "site_name":          "site",             # 'SEMPHIL'
    "prod_id":            "chip_model",       # 'CL03A104KA3NNPB'
    "input_prod_id":      "input_model",      # 'CL03A104MO3NNXB'
    "plan_d_day":         "closing_date",     # 'D - 6'
    "locking_yn":         "locking",          # 'Y' or ''
    # quantities — verified against Excel
    "mplan_qty":          "volpas_plan",      # 1194 ✓
    "plan_qty":           "lipas_g_plan",     # 21803 ✓
    "plan_qty_d7":        "lipas_plan_d5",    # 21803 ✓
    "end_qty":            "result",           # 20614 ✓
    "endrate":            "result_ratio_pct", # 94.55 ✓
    "end_qty_d0":         "plan_result_d5",   # 20614 ✓
    "inplan_endrate":     "plan_ratio_pct_d5",# 94.5 ✓
    "diff_qty":           "excess",           # -1189 ✓
    "lack_qty":           "lack_d5",          # 1189 ✓
    "goc_uld_yield":      "goc_up_yield_d5",  # 92.81 ✓
    "yidid_d5":           "lack_yield_d5",    # 1281 ✓
    "wip_qty":            "wip_total",        # best available (may differ from Excel sum)
    "avr_lt":             "last_month_tat_d5",# 42.8 ✓
    # WIP process breakdown (a0_v..a9_v, count given by colnum)
    "a0_v": "outgoing_inspection",
    "a1_v": "visual",
    "a2_v": "sorting",
    "a3_v": "plating",
    "a4_v": "term_firing",
    "a5_v": "termination",
    "a6_v": "tumbling",
    "a7_v": "firing",
    "a8_v": "cutting",
    "a9_v": "lamination",
}


# ── RPT40120 Process Result / Trackout: binary di-code → human-readable name ─
# Verified by decoding ws_capture_0427_output.pcapng (port 8081) and matching
# each binary value against RPT40120_OUTPUT_GRD_BASIC_2.xlsx row 1.
# Both Output (grd_basic_2) and Trackout share the same 236-column schema.
RPT40120_COL_MAP: dict[str, str] = {
    # [0]  _chk                  (internal checkbox, skip)
    # [1]
    "di00000256":      "major_process_name",          # Visual
    # [2]
    "di00001901":      "facility",                    # SEMPHIL Production#5
    # [3]
    "di00001699":      "middle_step_name",            # (empty for Visual)
    # [4]  sub_mat_unit_qty_sum  (SUM row marker, skip)
    # [5]
    "di00000258":      "process_name",                # Visual Finish / Visual Inspection
    # [6]
    "di00000652":      "pre_lot",                     # FM3TP65
    # [7]
    "di00001120":      "prev_major_process_complete_date",  # 2026-04-13 03:33
    # [8]
    "di00000262":      "lot_no",                      # OM3TP65
    # [9]
    "di00010259":      "global_first_chip_lot",       # AM3TP65
    # [10]
    "di00000265":      "model_id",                    # CL03A105MQ3OSNB
    # [11]
    "di00010520":      "global_first_chip_model",     # CL03A105MP3OSXB
    # [12]
    "di00006459":      "prev_chip_model",             # CL03A105MQ3OSAB
    # [13]
    "di00000304":      "powder_lot",                  # SH10DQ1C1BM
    # [14]
    "di00000305":      "batch_lot",                   # ARQ1C1309P
    # [15]
    "di00000308":      "print_lot",                   # MM32002PAP
    # [16]
    "di00000734":      "casting_type",                # Roll
    # [17]
    "di00001060":      "size",                        # 0603
    # [18]
    "di00001662":      "temp_char",                   # X5R
    # [19]
    "di00000365":      "cp_type",                     # High Capa.
    # [20]
    "di00001062":      "model_6",                     # 03A105
    # [21]
    "di00000626":      "powder",                      # SHBT100D
    # [22]
    "di00000574":      "composition",                 # NA392T010
    # [23]
    "di00002219":      "inner_paste_lot",             # GBS3NQ3DA1PN-003
    # [24]
    "di00002461":      "inner_paste_name",            # GNBS2(GBS3N)LP
    # [25]
    "di00004642":      "consumable_id1",
    # [26]
    "di00004638":      "consumable_model1",
    # [27]
    "di00004646":      "supplier_lot_no1",
    # [28]
    "di00004643":      "consumable_id2",
    # [29]
    "di00004639":      "consumable_model2",
    # [30]
    "di00004647":      "supplier_lot_no2",
    # [31]
    "di00004644":      "consumable_id3",
    # [32]
    "di00004640":      "consumable_model3",
    # [33]
    "di00004648":      "supplier_lot_no3",
    # [34]
    "di00004645":      "consumable_id4",
    # [35]
    "di00004641":      "consumable_model4",
    # [36]
    "di00004649":      "supplier_lot_no4",
    # [37]
    "di00002198":      "ext_term_paste_usage",
    # [38]
    "di00000267":      "repeat_count",                # 1
    # [39]
    "di00000369":      "lot_type",                    # MASS PRODUCTION
    # [40]
    "di00000370":      "lot_details",                 # MP
    # [41]
    "di00000297":      "urgency",                     # General
    # [42]
    "di00000249":      "input_qty",                   # 301848
    # [43]
    "di00000250":      "finish_qty",                  # 244400
    # [44]
    "di00000257":      "defect_qty",                  # 57448
    # [45]
    "di00000252":      "yield_pct",                   # 80.97
    # [46]
    "di00001128":      "pattern_area",                # 18.7444
    # [47]
    "di00002298":      "lot_weight_g",
    # [48]
    "di00001222":      "qty_of_input_bar",            # 2
    # [49]
    "di00001223":      "input_cutting_bar_qty",       # 23
    # [50]
    "di00001058":      "lamination_bar_qty",          # 2
    # [51]
    "di00001059":      "cutting_bar_qty",             # 19
    # [52]
    "di00002361":      "stacking_equip_group",        # 440 Stacking Equipment
    # [53]
    "di00003867":      "input_plants_id",             # E1802338
    # [54]
    "di00003868":      "input_equip_name",            # VI486_Inspection...
    # [55]
    "di00001160":      "equip_group",                 # S.A-1Tr-6Side-Color
    # [56]
    "di00001040":      "equipment_id",                # E1802338
    # [57]
    "di00001041":      "equipment_name",              # VI486_Inspection...
    # [58]
    "di00001224":      "equip_1",                     # VI486
    # [59]
    "di00008520":      "equip_1_work_qty",            # 0
    # [60]
    "di00001225":      "equip_2",
    # [61]
    "di00008521":      "equip_2_work_qty",
    # [62]
    "di00001226":      "equip_3",
    # [63]
    "di00008522":      "equip_3_work_qty",
    # [64]
    "di00001558":      "equip_4",
    # [65]
    "di00008523":      "equip_4_work_qty",
    # [66]
    "di00002290":      "equip_5",
    # [67]
    "di00008524":      "equip_5_work_qty",
    # [68]
    "di00002291":      "equip_6",
    # [69]
    "di00008525":      "equip_6_work_qty",
    # [70]
    "di00002292":      "equip_7",
    # [71]
    "di00008526":      "equip_7_work_qty",
    # [72]
    "di00002293":      "equip_8",
    # [73]
    "di00008527":      "equip_8_work_qty",
    # [74]
    "di00003933":      "equip_9",
    # [75]
    "di00008528":      "equip_9_work_qty",
    # [76]
    "di00003934":      "equip_10",
    # [77]
    "di00008529":      "equip_10_work_qty",
    # [78]
    "di00001227":      "operator_1",
    # [79]
    "di00001228":      "operator_2",
    # [80]
    "di00001229":      "operator_3",
    # [81]
    "di00001561":      "operator_4",
    # [82]
    "di00001230":      "cutting_bar_qty1",
    # [83]
    "di00001231":      "cutting_bar_qty2",
    # [84]
    "di00001232":      "cutting_bar_qty3",
    # [85]
    "di00000248":      "printing_equipment",          # 4GR17_Printer(Gravure)_600F
    # [86]
    "di00000254":      "stacking_equipment",          # 5HS03_Stacker(HS5-1Roll)_440_Blade
    # [87]
    "di00000272":      "receive_datetime",            # 2026-04-13 03:33:06
    # [88]
    "di00000273":      "input_datetime",              # 2026-04-27 01:12:56
    # [89]
    "di00003707":      "input_system",                # MES PC input
    # [90]
    "di00000863":      "input_worker",
    # [91]
    "di00001165":      "input_team",                  # SEMPHIL
    # [92]
    "di00000275":      "finish_time",                 # 2026-04-27 01:12:56
    # [93]
    "di00003708":      "finish_system",               # MES PC input
    # [94]
    "di00002295":      "time_class_4h",               # 00:00~04:00
    # [95]
    "di00009099":      "time_div_2h",                 # 00:00~02:00
    # [96]
    "di00000864":      "finish_worker",
    # [97]
    "di00001063":      "finished_team",
    # [98]
    "di00001240":      "work_facility",               # VI_Line D
    # [99]
    "di00003020":      "chief_of_staff",
    # [100]
    "di00003019":      "pm_in_charge",
    # [101]
    "di00002879":      "receive_process_worker",
    # [102]
    "di00001191":      "day_night",                   # NIGHT
    # [103]
    "di00002508":      "finish_date_day_night",       # 0426 NIGHT
    # [104]
    "di00002300":      "self_step_elapsed_days",      # 1
    # [105]
    "di00002501":      "stacking_congestion_day",     # 8.49
    # [106]
    "di00000277":      "derive_yn",                   # N
    # [107]
    "di00000280":      "rework_type",                 # Normal
    # [108]
    "di00000290":      "warehouse_rework_yn",         # N
    # [109]
    "di00000291":      "warehouse_rework_order_no",
    # [110]
    "di00000281":      "lot_generation_type",         # PRODUCT LOT
    # [111]
    "di00000283":      "customer",
    # [112]
    "di00000661":      "customer_name",
    # [113]
    "di00000285":      "powder_sap_model",            # MJ96-00035E
    # [114]
    "di00001061":      "powder_sap_model_name",       # ASSY PW;A,R,SHBT100(NA392T010)
    # [115]
    "di00001064":      "powder_size",                 # 100
    # [116]
    "di00000287":      "chip_type",                   # In-house chip ( R )
    # [117]
    "di00000288":      "screen_model",                # E03AMNI73-NOR-GL11SX
    # [118]
    "di00000264":      "derive_cause",                # (Visual) NG Rework
    # [119]
    "di00001209":      "l_cutting_qty",               # 75
    # [120]
    "di00001210":      "w_cutting_qty",               # 182
    # [121]
    "di00001256":      "whether_precision_trimming",
    # [122]
    "di00004559":      "first_firing_profile",
    # [123]
    "di00000289":      "firing_profile",              # PR_SV1153_0.20_R19_1H
    # [124]
    "di00001298":      "barrel_qty",                  # 0
    # [125]
    "di00001320":      "barrel_no",
    # [126]
    "di00001257":      "box_qty",                     # 1
    # [127]
    "di00001161":      "mesh_type",
    # [128]
    "di00001163":      "loading_stages",
    # [129]
    "di00006401":      "loading_input_mesh_count",    # 0
    # [130]
    "di00001250":      "finished_mesh_qty",           # 0
    # [131]
    "di00001251":      "input_mesh_area",             # 0
    # [132]
    "di00001252":      "finished_mesh_area",          # 0
    # [133]
    "di00001253":      "qty_ref_chips_per_mesh",
    # [134]
    "di00001254":      "qty_actual_chips_per_mesh",   # 0
    # [135]
    "di00000292":      "chip_bar_qty",                # 160704
    # [136]
    "di00002061":      "cutting_bar_chip_qty",        # 13392
    # [137]
    "di00000831":      "screen_pattern",              # 48
    # [138]
    "di00000827":      "screenshot_head_value",       # 4
    # [139]
    "di00000579":      "bar_size",                    # 440mm
    # [140]
    "di00002463":      "cover_lot",
    # [141]
    "di00002518":      "cover_lot1",                  # 6M32702PC
    # [142]
    "di00002519":      "cover_lot2",
    # [143]
    "di00002520":      "cover_lot3",
    # [144]
    "di00002521":      "cover_lot4",
    # [145]
    "di00002522":      "cover_lot5",
    # [146]
    "di00002820":      "cover_lot6",
    # [147]
    "di00002821":      "cover_lot7",
    # [148]
    "di00002822":      "cover_lot8",
    # [149]
    "di00002823":      "cover_lot9",
    # [150]
    "di00002824":      "cover_lot10",
    # [151]
    "di00000431":      "bottom_same_direction",       # 0
    # [152]
    "di00000434":      "cover_design_thickness",      # 3
    # [153]
    "di00000432":      "top_cover_layer",             # 10
    # [154]
    "di00000433":      "bottom_cover_layer",          # 10
    # [155]
    "di00002514":      "buffer_layer",                # 0
    # [156]
    "di00002515":      "buffer_sheet_thickness",      # 1.56
    # [157]
    "di00002467":      "cover_roll_qty_used",         # 286
    # [158]
    "di00006139":      "buffer_roll_qty_used",        # 0
    # [159]
    "di00000429":      "active_layer",                # 206
    # [160]
    "di00002288":      "batch_code",                  # S1K-2
    # [161]
    "di00002468":      "qty_finish_patterns",         # 313
    # [162]
    "di00001979":      "cutting_bar_size_type",       # 75*55
    # [163]
    "di00002059":      "input_remarks",
    # [164]
    "di00002060":      "finish_remarks",
    # [165]
    "di00001966":      "carrier_plate_type",
    # [166]
    "di00001205":      "casting_design_thickness",    # 1.15
    # [167]
    "di00000449":      "design_layer",                # 206L
    # [168]
    "di00000430":      "top_same_direction",          # 0
    # [169]
    "di00003524":      "loading_rate_pct",
    # [170]
    "di00000266":      "routing",                     # R00028
    # [171]
    "di00003748":      "routing_name",                # Visual_Normal-Newlot_1st Insp.
    # [172]
    "di00004147":      "heat_treatment_tray",
    # [173]
    "di00000386":      "consumable_id",
    # [174]
    "di00000388":      "consumable_model_id",
    # [175]
    "di00004007":      "model_13",                    # S
    # [176]
    "di00004069":      "automotive_yn",               # IT
    # [177]
    "di00006759":      "product_type",                # IT
    # [178]
    "di00001418":      "estimated_completion_time",   # 2026-04-27 01:12:56
    # [179]
    "di00004138":      "input_area",                  # 18.7444
    # [180]
    "di00004140":      "finish_area",                 # 15.155
    # [181]
    "di00004139":      "unit_area",                   # 0.0000620986
    # [182]
    "di00004320":      "overlap_stacking_cover_area", # 0
    # [183]
    "di00004321":      "center_buffer_cover_area",    # 0
    # [184]
    "di00004068":      "screen_type",                 # Gravure
    # [185]
    "di00005640":      "sap_experiment_id",
    # [186]
    "di00005641":      "gplm_document_no",
    # [187]
    "di00009139":      "input_total_area",            # 18.7444
    # [188]
    "di00009140":      "finish_total_area",           # 15.155
    # [189]
    "di00009899":      "input_total_unit_area",       # 0.0001
    # [190]
    "di00009900":      "finish_total_unit_area",      # 0.0001
    # [191]
    "durable_id":      "jig_id",
    # [192]
    "durable_prod_id": "jig_model_id",
    # [193]
    "di00000825":      "grade",
    # [194]
    "di00001960":      "qty",
    # [195]
    "di00006099":      "production_team_type",        # IT team
    # [196]
    "di00006579":      "capa_value_f",                # 1E-06
    # [197]
    "di00006580":      "input_cap_f",                 # 0.301848
    # [198]
    "di00006581":      "output_cap_f",                # 0.2444
    # [199]
    "di00007000":      "district",                    # Complex 1
    # [200]
    "di00007059":      "area_of_chip",                # 13.342
    # [201]
    "di00007179":      "dry_hard_profile",
    # [202]
    "di00005899":      "first_bake_profile",          # N2 340C 31.3hrs
    # [203]
    "di00005900":      "second_bake_profile",         # 890 4.5hrs
    # [204]
    "di00007339":      "the_final_step",              # Outgoing Inspection
    # [205]
    "di00007359":      "lot_finish_date",             # 2026-06-29 00:00
    # [206]
    "di00007400":      "termination_coating_condition",
    # [207]
    "di00007459":      "mesh_load_layer",
    # [208]
    "di00007460":      "lot_load_location",
    # [209]
    "di00000562":      "stars_pattern_chip_qty",      # 13392
    # [210]
    "di00004478":      "center_buffer_layer",         # 0
    # [211]
    "di00004543":      "area_type_value",             # 440
    # [212]
    "di00007721":      "partial_active_buffer_layer", # 0
    # [213]
    "di00007939":      "equipment_finish_system",
    # [214]
    "di00007959":      "completed_date_in_machine",
    # [215]
    "di00000374":      "prev_process_finish_date",    # 2026-04-26 23:31:06
    # [216]
    "di00000312":      "expt_incharge",
    # [217]
    "di00009999":      "top_lot",
    # [218]
    "di00010019":      "input_container_qty_list",
    # [219]
    "di00010020":      "complete_container_qty_list",
    # [220]
    "di00010021":      "input_layer_qty_list",
    # [221]
    "di00010022":      "complete_layer_qty_list",
    # [222]
    "di00009959":      "prev_process_facility",       # SEMPHIL Production#5
    # [223]
    "di00009960":      "prev_process_large",          # Visual
    # [224]
    "di00010139":      "prev_process_middle_step",    # (empty for Visual rows)
    # [225]
    "di00009961":      "prev_process_name",           # OI Visual Inspection
    # [226]
    "di00009962":      "prev_process_equip_name",
    # [227]
    "di00009963":      "prev_process_equip_group",
    # [228]
    "di00010559":      "special_code",
    # [229]
    "di00010660":      "input_ring_usage_vs_qty",     # 0
    # [230]
    "di00010659":      "finish_ring_usage_vs_qty",    # 0
    # [231]
    "di00000580":      "casting_lot",                 # MM32002PA
    # [232]
    "di00001122":      "stacking_lot",                # MM32002PAP-AB
    # [233]
    "di00010859":      "same_direction",              # 0
    # [234]
    "di00011079":      "stacking_parent_lot",         # AM3TP65
    # [235]
    "di00011239":      "curing_loading_input_mesh_count",  # 0
}


def _patch_rpt40120_post_body(post_data: bytes, jsessionid: str = "") -> bytes:
    """
    Patch the RPT40120 POST body (port 8081) before replaying.

    Date logic — RPT40120 uses a rolling 24-hour window:
      StartDate = today     00:00:00  (YYYYMMDD000000)  ← current day start
      EndDate   = tomorrow  00:00:00  (YYYYMMDD000000)  ← next day start

    Running at any time on 2026-04-28:
      StartDate = 20260428000000
      EndDate   = 20260429000000

    This captures all production results for the current calendar day in
    real-time, matching the MES UI "Today" filter behavior.

    The snapshot tables (process_result_snapshot, process_trackout_snapshot) store
    one copy per day, giving a permanent record of each day's production.

    Other fields patched:
      end_date    YYYYMMDDHHmmss  -> current datetime
      log_seq     10-digit number -> current unix timestamp
      JSESSIONID  (embedded in body) -> fresh session ID from login

    The server on port 8081 validates the JSESSIONID from the body,
    not just the cookie header.
    """
    import time as _time
    from datetime import datetime as _dt, timedelta as _td

    if len(post_data) < 4 or post_data[:2] != b'\xff\xad':
        return post_data

    try:
        dec = zlib.decompress(post_data[2:])
    except zlib.error:
        return post_data

    now      = _dt.now(MANILA_TZ)
    today    = now.strftime("%Y%m%d")                    # StartDate
    tomorrow = (now + _td(days=1)).strftime("%Y%m%d")   # EndDate
    now_str  = now.strftime("%Y%m%d%H%M%S")
    log_seq  = str(int(_time.time()))

    today_start    = (today    + "000000").encode()
    tomorrow_start = (tomorrow + "000000").encode()

    # Find the two YYYYMMDD000000 date values in the payload
    all_dates = re.findall(rb'20[2-9][0-9][0-1][0-9][0-3][0-9]000000', dec)
    if len(all_dates) >= 2:
        old_start = all_dates[0]
        old_end   = all_dates[1]

        # Replace StartDate first (replace only the first occurrence)
        if old_start != today_start:
            dec = dec.replace(old_start, today_start, 1)
            log.info(f"  [rpt40120 patch] StartDate: {old_start.decode()} -> {today_start.decode()}")
        else:
            log.info(f"  [rpt40120 patch] StartDate: {old_start.decode()} (already today, no change)")

        # Replace EndDate — find it fresh after StartDate replacement
        all_dates2 = re.findall(rb'20[2-9][0-9][0-1][0-9][0-3][0-9]000000', dec)
        if all_dates2:
            # The EndDate is the one that is NOT today_start, or the second occurrence
            for d in all_dates2:
                if d != today_start:
                    if d != tomorrow_start:
                        dec = dec.replace(d, tomorrow_start, 1)
                        log.info(f"  [rpt40120 patch] EndDate  : {d.decode()} -> {tomorrow_start.decode()}")
                    else:
                        log.info(f"  [rpt40120 patch] EndDate  : {d.decode()} (already tomorrow, no change)")
                    break
            else:
                # All dates are today_start — the second one is EndDate
                idx = dec.find(today_start)
                idx2 = dec.find(today_start, idx + 1)
                if idx2 != -1:
                    dec = dec[:idx2] + tomorrow_start + dec[idx2 + len(today_start):]
                    log.info(f"  [rpt40120 patch] EndDate  : {today_start.decode()} -> {tomorrow_start.decode()}")
    elif len(all_dates) == 1:
        # Only one date found — treat as StartDate
        old_start = all_dates[0]
        if old_start != today_start:
            dec = dec.replace(old_start, today_start, 1)
            log.info(f"  [rpt40120 patch] StartDate: {old_start.decode()} -> {today_start.decode()}")

    # Patch end_date (YYYYMMDDHHmmss) — after StartDate/EndDate to avoid 000000 collision
    end_date_vals = re.findall(rb'20[2-9][0-9][0-1][0-9][0-3][0-9][0-2][0-9][0-5][0-9][0-5][0-9]', dec)
    end_date_vals = [v for v in end_date_vals if not v.endswith(b'000000')]
    if end_date_vals:
        old_ed = end_date_vals[0]
        new_ed = now_str.encode()
        dec = dec.replace(old_ed, new_ed, 1)
        if old_ed != new_ed:
            log.info(f"  [rpt40120 patch] end_date : {old_ed.decode()} -> {new_ed.decode()}")

    # Patch log_seq (10-digit unix-range number)
    log_seqs = re.findall(rb'[0-9]{10}', dec)
    for old_ls in log_seqs:
        val = int(old_ls)
        if 8000000000 <= val <= 9999999999:
            new_ls = log_seq.encode()
            dec = dec.replace(old_ls, new_ls, 1)
            log.info(f"  [rpt40120 patch] log_seq  : {old_ls.decode()} -> {new_ls.decode()}")
            break

    # Patch JSESSIONID embedded inside the POST body
    if jsessionid:
        jsid_marker = b'JSESSIONID'
        idx = dec.find(jsid_marker)
        if idx != -1:
            p = idx + len(jsid_marker)
            # Skip slot1 value
            if p < len(dec):
                vt = dec[p]; p += 1
                if vt in (0x15, 0x28) and p + 2 <= len(dec):
                    vl = struct.unpack_from('>H', dec, p)[0]; p += 2 + vl
                elif vt == 0x00:
                    pass
            # Read slot2 (the actual JSESSIONID value)
            if p < len(dec):
                vt = dec[p]
                if vt in (0x15, 0x28) and p + 3 <= len(dec):
                    vl = struct.unpack_from('>H', dec, p + 1)[0]
                    old_jsid = dec[p + 3:p + 3 + vl]
                    new_jsid = jsessionid.encode('utf-8')
                    if old_jsid != new_jsid:
                        old_chunk = bytes([vt]) + struct.pack('>H', vl) + old_jsid
                        new_chunk = bytes([vt]) + struct.pack('>H', len(new_jsid)) + new_jsid
                        dec = dec[:p] + new_chunk + dec[p + len(old_chunk):]
                        log.info(f"  [rpt40120 patch] JSESSIONID: {old_jsid[:16].decode('utf-8', errors='replace')}... -> {jsessionid[:16]}...")

    patched = b'\xff\xad' + zlib.compress(dec, level=6)
    log.info(f"  [rpt40120 patch] POST body: {len(post_data)} -> {len(patched)} bytes  "
             f"(StartDate={today}000000, EndDate={tomorrow}000000)")
    return patched


def load_captured_requests() -> dict:
    if not os.path.exists(REQUESTS_FILE):
        raise FileNotFoundError(
            f"{REQUESTS_FILE} not found.\n"
            "Run the proxy interceptor first:\n"
            "  python proxy_intercept.py"
        )
    with open(REQUESTS_FILE, encoding="utf-8") as f:
        return json.load(f)


def _do_login(session: requests.Session) -> bool:
    """
    XPlatform native login flow — the only login that port 8081 accepts.

    Steps:
      1. GET /xp/frame/common/Login.xfdl  → get initial JSESSIONID cookie
      2. POST /login.do with XP binary body (SHA-256 hashed password)
      3. POST /system/xp/getsession.do    → complete session setup

    The web portal login (POST /index.jsp) gives a JSESSIONID that port 8080
    accepts but port 8081 rejects. This XP native login works for both ports.
    """
    import hashlib, base64

    if not MES_USERNAME or not MES_PASSWORD:
        log.warning("[Session] MES_USERNAME / MES_PASSWORD not set — cannot auto-login.")
        return False

    host = MES_URL.rstrip("/").replace("http://", "").replace("https://", "")

    try:
        # ── Step 1: GET login page → initial JSESSIONID ───────────────────────
        r = session.get(f"{MES_URL}/xp/frame/common/Login.xfdl", timeout=10)
        jsid = session.cookies.get("JSESSIONID", "")
        if not jsid:
            # Fallback: try index.jsp
            session.get(f"{MES_URL}/index.jsp", timeout=10)
            jsid = session.cookies.get("JSESSIONID", "")
        if not jsid:
            log.warning("[Session] No initial JSESSIONID from login page")
            return False
        log.info(f"[Session] Initial JSESSIONID={jsid[:12]}...")

        # ── Step 2: Build XP binary login body ───────────────────────────────
        # Password is SHA-256 hashed then Base64-encoded
        pwd_hash = base64.b64encode(
            hashlib.sha256(MES_PASSWORD.encode('utf-8')).digest()
        ).decode('utf-8')

        fields = [
            ('emp_no',           MES_USERNAME),
            ('user_pwd',         pwd_hash),
            ('gv_site_code',     'E502AA'),
            ('code_group_id',    'GRP00004'),
            ('gv_emp_no',        MES_USERNAME),
            ('gv_div_code',      'ALL'),
            ('gv_endp_code',     'LCR'),
            ('gv_menu_id',       'LOGIN'),
            ('gv_language_code', 'ENG'),
            ('gv_app_id',        'ADM'),
            ('gv_app_adm',       'ADM'),
        ]

        def _xp_str(val):
            enc = val.encode('utf-8') if val else b''
            return b'\x15' + struct.pack('>H', len(enc)) + enc

        def _xp_null():
            return b'\x00'

        col_count = len(fields)
        # Metadata block (JSESSIONID + useEncryption)
        meta_fields = [('JSESSIONID', jsid), ('useEncryption', 'false')]
        meta_hdr = b'\xfe\x10' + struct.pack('>HHH', 0x13, 0, 4) + struct.pack('>H', len(meta_fields))
        meta_cols = b''
        for name, _ in meta_fields:
            nb = name.encode('utf-8')
            meta_cols += struct.pack('>H', len(nb)) + nb + b'\x15' + struct.pack('>I', 256) + b'\x00'
        meta_row = b'\x00' * 6
        for _, val in meta_fields:
            meta_row += _xp_null() + _xp_str(val)
        meta_end = b'\xfe\x01' + struct.pack('>HI', 0x13, 0)

        # Data block (login fields)
        data_hdr = b'\xfe\x10' + struct.pack('>HHH', 0, 0, 0) + struct.pack('>H', col_count)
        data_cols = b''
        for name, _ in fields:
            nb = name.encode('utf-8')
            data_cols += struct.pack('>H', len(nb)) + nb + b'\x15' + struct.pack('>I', 256) + b'\x00'
        data_row = b'\x00' * 6
        for _, val in fields:
            data_row += _xp_null() + _xp_str(val)
        data_end = b'\xfe\x01' + struct.pack('>HI', 0, 0)

        payload = meta_hdr + meta_cols + meta_row + meta_end + data_hdr + data_cols + data_row + data_end
        login_body = b'\xff\xad' + zlib.compress(payload, level=6)

        xp_headers = {
            "Accept":          "*/*",
            "Accept-Encoding": "gzip, deflate",
            "Cache-Control":   "no-cache",
            "Content-Type":    "application/octet-stream",
            "Referer":         f"{MES_URL}/xp/frame/common/Login.xfdl",
            "User-Agent":      ("XPLATFORM/9.2.2 Runtmie (compatible; Mozilla/4.0; "
                                "MSIE7.0; System=Win64; Device=; OS=Windows 10; "
                                "Screen=1920*1080*16M)"),
        }

        resp = session.post(f"{MES_URL}/login.do", data=login_body,
                            headers=xp_headers, timeout=15)
        new_jsid = session.cookies.get("JSESSIONID", "")
        log.info(f"[Session] POST /login.do -> {resp.status_code}  {len(resp.content)} bytes  "
                 f"JSESSIONID={new_jsid[:12] if new_jsid else 'none'}...")

        # Check for login error in response
        if resp.content[:2] == b'\xff\xad':
            try:
                dec_check = zlib.decompress(resp.content[2:])
                if b'ErrorCode' in dec_check:
                    idx = dec_check.find(b'ErrorMsg')
                    if idx != -1:
                        snippet = dec_check[idx:idx+80].decode('utf-8', errors='replace')
                        log.warning(f"[Session] Login response: {snippet}")
            except Exception:
                pass

        # ── Step 3: POST /system/xp/getsession.do ────────────────────────────
        # Build a minimal getsession body using the new JSESSIONID
        gs_jsid = session.cookies.get("JSESSIONID", jsid)
        gs_fields = [
            ('JSESSIONID',    gs_jsid),
            ('useEncryption', 'false'),
        ]
        gs_hdr = b'\xfe\x10' + struct.pack('>HHH', 0x13, 0, 4) + struct.pack('>H', len(gs_fields))
        gs_cols = b''
        for name, _ in gs_fields:
            nb = name.encode('utf-8')
            gs_cols += struct.pack('>H', len(nb)) + nb + b'\x15' + struct.pack('>I', 256) + b'\x00'
        gs_row = b'\x00' * 6
        for _, val in gs_fields:
            gs_row += _xp_null() + _xp_str(val)
        gs_end = b'\xfe\x01' + struct.pack('>HI', 0x13, 0)
        gs_payload = gs_hdr + gs_cols + gs_row + gs_end
        gs_body = b'\xff\xad' + zlib.compress(gs_payload, level=6)

        gs_headers = dict(xp_headers)
        gs_headers["Referer"] = f"{MES_URL}/xp/frame/common/Login.xfdl"
        try:
            gs_resp = session.post(f"{MES_URL}/system/xp/getsession.do",
                                   data=gs_body, headers=gs_headers, timeout=15)
            log.info(f"[Session] POST /system/xp/getsession.do -> {gs_resp.status_code}  "
                     f"{len(gs_resp.content)} bytes")
        except Exception as e:
            log.warning(f"[Session] getsession.do failed (non-fatal): {e}")

        final_jsid = session.cookies.get("JSESSIONID", "")
        if final_jsid:
            log.info(f"[Session] Login OK — JSESSIONID={final_jsid[:12]}...")
            return True

        log.warning("[Session] No JSESSIONID after XP login")
        return False

    except Exception as e:
        log.error(f"[Session] Login failed: {e}")
        return False


def get_session() -> requests.Session:
    """Create a requests.Session and attempt MES login to obtain a valid JSESSIONID."""
    session = requests.Session()
    session.headers.update({
        # Use a browser UA — the XPlatform server may reject non-browser agents for login
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    })
    _do_login(session)
    return session


def _is_session_expired(raw: bytes, rows: list[dict], report_name: str = "") -> bool:
    """
    Detect an expired / invalid session.
    Heuristics:
      - Response starts with HTML (b'<' or b'<!') → redirect to login page
      - For RPT40120: NEVER treat 0 rows as session expiry.
        The server returns ErrorMsg='Operation succeeded.' with 0 rows when
        the date range has no data. This is valid — not an auth failure.
      - For other reports: 0 rows from a tiny response is suspicious.
    """
    if not raw:
        return True
    # HTML response means the server redirected us to the login page
    stripped = raw.lstrip()
    if stripped.startswith(b'<'):
        return True
    # RPT40120 uses date-filtered queries — 0 rows is valid (no data for that day)
    if report_name in ("rpt40120_output", "rpt40120_trackout"):
        return False
    # For other reports: tiny 0-row response = auth failure
    if len(rows) == 0 and len(raw) < 5000:
        return True
    return False


def parse_xplatform_binary(data: bytes) -> list[dict]:
    """
    Parse XPlatform proprietary binary protocol (application/octet-stream).

    Wire format:
      Bytes 0-1 : ff ad  (XPlatform magic — skip)
      Bytes 2-N : zlib-compressed payload

    Decompressed layout (one or more blocks):
      Block header : fe 10 [2B dataset_id] [2B b1] [2B b2] [2B col_count]
      Col defs     : col_count × ([2B name_len][name UTF-8][1B type][4B max_size][1B extra])
      Row data     : until fe 01 end marker
        Row header : 6 bytes (row identifier, skip)
        Values     : 2 × col_count values  (current set + original/planned set)
          0x00           → null  (1 byte total)
          0x15 / 0x28    → string  (1B type + 2B len + data)
          0x03           → int32   (1B type + 4B data, no len field)
          0x04           → float64 (1B type + 8B data, no len field)
          0x01           → bool    (1B type + 1B data, no len field)
          other          → skip via 2B len field (best-effort)
      Block end    : fe 01 [2B dataset_id] [4B ???]

    Metadata blocks (cols: gv_logSeq, gv_ip_addr, ErrorCode, ErrorMsg) are skipped.
    Only the first col_count values per row (current set) are returned.
    """
    if len(data) < 4:
        return []

    try:
        dec = zlib.decompress(data[2:])
    except zlib.error as e:
        log.error(f"zlib decompress failed: {e}")
        return []

    n = len(dec)
    pos = 0
    all_rows: list[dict] = []

    META_COLS = {'gv_logSeq', 'gv_ip_addr', 'ErrorCode', 'ErrorMsg'}

    def read_val(p: int):
        """Read one typed value. Returns (str_value_or_None, new_pos)."""
        if p >= n:
            return None, p
        vt = dec[p]; p += 1
        if vt == 0x00:
            return None, p
        elif vt in (0x15, 0x28):
            if p + 2 > n:
                return None, p
            vl = struct.unpack_from('>H', dec, p)[0]; p += 2
            if p + vl > n:
                return None, p
            val = dec[p:p + vl].decode('utf-8', errors='replace'); p += vl
            return val, p
        elif vt == 0x03:
            if p + 4 > n:
                return None, p
            val = struct.unpack_from('>i', dec, p)[0]; p += 4
            return str(val), p
        elif vt == 0x04:
            if p + 8 > n:
                return None, p
            val = struct.unpack_from('>d', dec, p)[0]; p += 8
            return str(val), p
        elif vt == 0x01:
            if p + 1 > n:
                return None, p
            val = dec[p]; p += 1
            return str(val), p
        else:
            # Unknown type — try to skip using a 2-byte length field
            if p + 2 <= n:
                vl = struct.unpack_from('>H', dec, p)[0]
                if vl < 65000 and p + 2 + vl <= n:
                    p += 2 + vl
            return None, p

    while pos < n - 1:
        # Scan for fe 10 block marker
        if dec[pos] != 0xfe or dec[pos + 1] != 0x10:
            pos += 1
            continue

        pos += 2
        if pos + 8 > n:
            break

        # Block header
        pos += 2  # dataset_id (unused)
        pos += 2  # b1 (unused)
        pos += 2  # b2 (unused)
        col_count = struct.unpack_from('>H', dec, pos)[0]; pos += 2

        if col_count == 0 or col_count > 10000:
            continue

        # Parse column definitions
        cols: list[str] = []
        valid = True
        for _ in range(col_count):
            if pos + 2 > n:
                valid = False; break
            name_len = struct.unpack_from('>H', dec, pos)[0]; pos += 2
            if name_len > 256 or pos + name_len > n:
                valid = False; break
            name = dec[pos:pos + name_len].decode('utf-8', errors='replace'); pos += name_len
            if pos + 6 > n:
                valid = False; break
            pos += 6  # [1B type][4B max_size][1B extra]
            cols.append(name)

        if not valid or len(cols) != col_count:
            continue

        # Skip metadata blocks — but first extract ErrorCode/ErrorMsg for logging
        if set(cols) & META_COLS:
            # Parse the single metadata row to extract error info
            meta_row: dict = {}
            row_start = pos
            # Try to parse one row
            if pos < n - 1 and not (dec[pos] == 0xfe and dec[pos+1] in (0x01, 0x10)):
                if pos + 6 <= n:
                    pos += 6  # row header
                    for col_name in cols:
                        _, pos = read_val(pos)
                        val, pos = read_val(pos)
                        meta_row[col_name] = val if val is not None else ''
            # Log any error
            err_code = meta_row.get('ErrorCode', '')
            err_msg  = meta_row.get('ErrorMsg', '')
            if err_code and str(err_code) not in ('0', ''):
                log.warning(f"Server ErrorCode={err_code}  ErrorMsg={err_msg}")
            elif err_msg and err_msg not in ('Operation succeeded.', ''):
                log.warning(f"Server ErrorMsg={err_msg}")
            # Skip to end of this block
            while pos < n - 1:
                if dec[pos] == 0xfe and dec[pos + 1] == 0x01:
                    pos += 8
                    break
                pos += 1
            continue

        # Parse row data
        block_rows: list[dict] = []
        while pos < n - 1:
            if dec[pos] == 0xfe and dec[pos + 1] == 0x01:
                pos += 8  # consume end marker
                break
            if dec[pos] == 0xfe and dec[pos + 1] == 0x10:
                break  # next block starts

            if pos + 6 > n:
                break
            pos += 6  # row header (6 bytes)

            # XPlatform sends 2×col_count values per row: each column has two slots.
            # Slot1 is always null/empty; slot2 holds the real value.
            row: dict = {}
            for col_name in cols:
                _, pos = read_val(pos)           # slot1 — always null, discard
                val, pos = read_val(pos)         # slot2 — real value
                row[col_name] = val if val is not None else ''

            block_rows.append(row)

        all_rows.extend(block_rows)
        log.info(f"Parsed block: {len(cols)} cols × {len(block_rows)} rows")

    log.info(f"Total rows parsed: {len(all_rows)}")
    return all_rows


def remap_rpt40120_row(row: dict) -> dict:
    """Rename binary di-codes to human-readable column names for RPT40120 rows."""
    return {RPT40120_COL_MAP.get(k, k): v for k, v in row.items()}


def filter_rpt40120_rows(rows: list[dict]) -> list[dict]:
    """
    Skip the SUM row and any rows without a lot_no.
    The SUM row has sub_mat_unit_qty_sum set but lot_no empty.
    Real data rows always have a non-empty lot_no.
    """
    return [r for r in rows if r.get("lot_no") not in (None, "")]


def remap_wip_row(row: dict) -> dict:
    """Rename binary di-codes to human-readable column names for wip_status rows."""
    return {WIP_COL_MAP.get(k, k): v for k, v in row.items()}


def remap_monthly_row(row: dict) -> dict:
    """Rename binary column names to human-readable names for monthly_plan rows."""
    return {MONTHLY_COL_MAP.get(k, k): v for k, v in row.items()}


def filter_wip_rows(rows: list[dict]) -> list[dict]:
    """
    Skip header/summary rows that XPlatform includes at the top of RPT40281.
    Real data rows always have a non-empty lot_no.
    """
    return [r for r in rows if r.get("lot_no") not in (None, "")]


def filter_monthly_rows(rows: list[dict]) -> list[dict]:
    """
    Skip the summary row at the top of RPT40496.
    Real data rows always have site populated.
    """
    return [r for r in rows if (r.get("site") or "").strip() not in ("", None)]


def _patch_monthly_post_body(post_data: bytes) -> bytes:
    """
    The captured POST body for RPT40496 contains hardcoded month/date values
    (e.g. 202603, 20260301, 20260331) baked into the zlib-compressed payload.
    This function decompresses, replaces all date tokens with the current
    Manila-time month, then recompresses — so the request always asks for
    the current month regardless of when the capture was taken.

    Tokens patched (all are ASCII inside the decompressed payload):
      YYYYMM        → current month  (e.g. 202603 → 202604)
      YYYYMM01      → first day of current month
      YYYYMMlast    → last day of current month (handles 28/29/30/31)
    """
    now = datetime.now(MANILA_TZ)
    cur_ym   = now.strftime("%Y%m")           # e.g. "202604"
    cur_ym01 = now.strftime("%Y%m01")         # e.g. "20260401"
    last_day = calendar.monthrange(now.year, now.month)[1]
    cur_ymlast = now.strftime(f"%Y%m{last_day:02d}")  # e.g. "20260430"

    if len(post_data) < 4:
        return post_data

    try:
        dec = zlib.decompress(post_data[2:])
    except zlib.error:
        return post_data  # not zlib — return as-is

    # Find any 6-digit YYYYMM already in the payload to use as the "captured" month
    found = re.findall(rb'(20[2-9][0-9][0-1][0-9])', dec)
    if not found:
        return post_data  # no dates found — nothing to patch

    # Use the most common 6-digit match as the captured month
    captured_ym = max(set(found), key=found.count).decode()
    if captured_ym == cur_ym:
        log.info("[monthly patch] POST body already has current month — no patch needed.")
        return post_data  # already current, skip recompression

    captured_ym01   = captured_ym + "01"
    captured_year   = captured_ym[:4]
    captured_month  = int(captured_ym[4:6])
    cap_last_day    = calendar.monthrange(int(captured_year), captured_month)[1]
    captured_ymlast = captured_ym + f"{cap_last_day:02d}"

    # Replace in order: longest patterns first to avoid partial matches
    dec = dec.replace(captured_ymlast.encode(), cur_ymlast.encode())
    dec = dec.replace(captured_ym01.encode(),   cur_ym01.encode())
    dec = dec.replace(captured_ym.encode(),     cur_ym.encode())

    # Recompress with same zlib level, prepend ff ad magic
    recompressed = zlib.compress(dec, level=6)
    patched = b'\xff\xad' + recompressed
    log.info(
        f"[monthly patch] POST body patched: {captured_ym} → {cur_ym} "
        f"(start={cur_ym01}, end={cur_ymlast})"
    )
    return patched


def _do_fetch(session: requests.Session, report_name: str,
              captured_entries: list) -> tuple[bytes, list[dict]]:
    """
    Execute the POST for one report. Returns (raw_bytes, parsed_rows).
    Raises requests.RequestException on network error.
    """
    req = captured_entries[-1]
    url = req["url"]

    if "post_data_hex" in req:
        post_data = bytes.fromhex(req["post_data_hex"])
    else:
        post_data_str = req.get("post_data", "")
        post_data = post_data_str.encode("utf-8", errors="surrogateescape") if post_data_str else b""

    # Patch monthly_plan POST body to use current month (dates are hardcoded in capture)
    if "monthly" in report_name.lower() or "rpt_capture_1" in report_name:
        post_data = _patch_monthly_post_body(post_data)
    # For rpt_capture_* where we don't know the type yet, patch if it looks like monthly
    elif post_data[:2] == b'\xff\xad':
        try:
            dec_check = zlib.decompress(post_data[2:])
            if b'RPT40496' in dec_check or b'monresultrate' in dec_check.lower():
                post_data = _patch_monthly_post_body(post_data)
        except Exception:
            pass

    # Patch RPT40120 POST body (port 8081 — needs date + JSESSIONID patching)
    if report_name in ("rpt40120_output", "rpt40120_trackout"):
        jsessionid = session.cookies.get("JSESSIONID", "")
        post_data = _patch_rpt40120_post_body(post_data, jsessionid=jsessionid)

    headers = {
        k: v for k, v in req.get("headers", {}).items()
        if k.lower() not in ("content-length", "host", "proxy-connection")
    }

    log.info(f"[{report_name}] POST -> {url}")
    resp = session.post(url, data=post_data, headers=headers, timeout=60)
    resp.raise_for_status()
    raw = resp.content
    log.info(
        f"[{report_name}] {resp.status_code} — {len(raw)} bytes  "
        f"content-type={resp.headers.get('Content-Type','')}"
    )
    rows = parse_xplatform_binary(raw)
    return raw, rows


def fetch_report(session: requests.Session, report_name: str,
                 captured_entries: list) -> list[dict]:
    """
    Replay the last captured request for a report and parse the response.
    If the session appears expired (HTML response or 0 rows), re-login once and retry.
    """
    try:
        raw, rows = _do_fetch(session, report_name, captured_entries)
    except requests.RequestException as e:
        log.error(f"[{report_name}] Request failed: {e}")
        return []

    # Always save raw binary immediately — even error responses are useful for diagnosis
    debug_path = os.path.join(os.path.dirname(__file__), f"debug_{report_name}.bin")
    with open(debug_path, "wb") as f:
        f.write(raw)

    # ── Session expiry detection ──────────────────────────────────────────────
    if _is_session_expired(raw, rows, report_name):
        log.warning(
            f"[{report_name}] Session appears expired "
            f"({'HTML response' if raw.lstrip().startswith(b'<') else 'small 0-row response'}) "
            "— attempting re-login..."
        )
        ok = _do_login(session)
        if ok:
            log.info(f"[{report_name}] Re-login succeeded — retrying request...")
            try:
                raw, rows = _do_fetch(session, report_name, captured_entries)
            except requests.RequestException as e:
                log.error(f"[{report_name}] Retry after re-login failed: {e}")
                return []
            if _is_session_expired(raw, rows, report_name):
                log.error(
                    f"[{report_name}] Still getting error response after re-login. "
                    "Check credentials or MES login flow."
                )
                return []
        else:
            log.error(
                f"[{report_name}] Re-login failed — no valid session. "
                "Update MES_USERNAME / MES_PASSWORD in .env."
            )
            return []

    # Raw binary already saved above (before session check)
    log.info(f"[{report_name}] Raw binary saved → {debug_path}")

    if not rows:
        log.warning(f"[{report_name}] Could not parse binary response — check {debug_path}")

    return rows


def fetch_all(offline: bool = False) -> dict[str, list[dict]]:
    captured = load_captured_requests()

    if offline:
        # Parse existing debug_*.bin files directly — no network needed
        results = {}
        for name in captured:
            if name in ("unknown",):
                continue
            bin_path = os.path.join(os.path.dirname(__file__), f"debug_{name}.bin")
            if not os.path.exists(bin_path):
                log.warning(f"[{name}] No bin file found at {bin_path} — skipping.")
                continue
            with open(bin_path, "rb") as f:
                raw = f.read()
            log.info(f"[{name}] Parsing offline bin: {len(raw)} bytes")
            rows = parse_xplatform_binary(raw)
            log.info(f"[{name}] Parsed {len(rows)} rows from bin file")
            results[name] = rows
        return results

    session = get_session()
    results = {}
    for name, entries in captured.items():
        if name in ("unknown",):
            continue
        results[name] = fetch_report(session, name, entries)
    return results


if __name__ == "__main__":
    results = fetch_all()
    for name, rows in results.items():
        print(f"\n{name}: {len(rows)} rows")
        if rows:
            print("  Columns:", list(rows[0].keys()))
            print("  Row 0:  ", rows[0])
