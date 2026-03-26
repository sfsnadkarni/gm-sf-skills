#!/usr/bin/env python3
"""
Creates a small sample intermediate Excel for testing the pipeline
with a handful of Vehicle custom fields + picklist values.

These are real Vehicle fields pulled from the source STF but selected
so they are NOT already in any existing translated STF.
"""
import os
import sys
import openpyxl


SAMPLE_FIELDS = [
    # (Field Label, Field API Name)
    # These 4 fields are confirmed: (a) in the master sheet, (b) in the UNTRANSLATED
    # section of the bilingual org export — safe to upload without overwriting anything.
    ("Delivery Type",                  "GM_Delivery_Type__c"),
    ("MSRP",                           "GM_MSRP__c"),
    ("Fleet Account Number (FAN)",     "Fleet_Account_Number_FAN__c"),
    ("CARE Mobile Service + Entitlement", "CC_CAREMobileServiceEntitlement__c"),
]

SAMPLE_PICKLIST_VALUES = [
    # (STF Field Name, Picklist Value, Picklist Label)
    # 5 picklist values — all confirmed untranslated in org, single-value in master sheet.
    ("CC_CAREMobileServiceEntitlement", "Expired",  "Expired"),
    ("OnStar_Fuel_Type",               "Diesel",    "Diesel"),
    ("OnStar_Fuel_Type",               "Electric",  "Electric"),
    ("OnStar_Fuel_Type",               "Gasoline",  "Gasoline"),
    ("OnStar_Fuel_Type",               "E85",       "E85"),
]


def main():
    output_dir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/sf-translation-test"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "Vehicle_intermediate.xlsx")

    wb = openpyxl.Workbook()

    ws_fields = wb.active
    ws_fields.title = "Custom_Fields"
    ws_fields.append(["Field Label", "Field API Name"])
    for label, api_name in SAMPLE_FIELDS:
        ws_fields.append([label, api_name])

    ws_pv = wb.create_sheet("Picklist_Values")
    ws_pv.append(["Field API Name", "Picklist Value", "Picklist Label"])
    for stf_name, pv_value, pv_label in SAMPLE_PICKLIST_VALUES:
        ws_pv.append([stf_name, pv_value, pv_label])

    wb.save(output_path)
    print(f"Sample intermediate Excel written to: {output_path}")
    print(f"  {len(SAMPLE_FIELDS)} custom fields")
    print(f"  {len(SAMPLE_PICKLIST_VALUES)} picklist values")


if __name__ == "__main__":
    main()
