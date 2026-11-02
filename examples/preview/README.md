# Preview set (hand-made, 4 cases)
Same format and spec as the real generator, written by hand so you can look at it now. The real data will differ in wording, layouts and suppliers. Not part of the benchmark.

## PREVIEW-01 · clean · caseworks
**Answer key:** real discrepancy = False, reason = `none`, next step = `pay`, dollars at risk = $0.00, noise = none

**Purchase order**

```
CASEWORKS INC.  PURCHASE ORDER  PO-008812  2026-10-20
Vendor: Lumen Accessories Ltd.
SKU       Description                 Qty   UOM  Unit    Amount
PC-IP15   Clear phone case, iPhone 15  1200  EA   3.10    3,720.00
CH-20W    20W USB-C charger             600  EA   6.85    4,110.00
Total                                                    7,830.00
```

**Shipping notice**

```
ADVANCE SHIP NOTICE  ASN-55021  Lumen Accessories Ltd.
Ref PO-008812   Ship date 2026-10-27   Carrier: CoastFreight
PC-IP15  shipped 1200 EA      CH-20W  shipped 600 EA
```

**Goods receipt**

```
CASEWORKS DC-EAST  GOODS RECEIPT  GR-31877  2026-10-30
PO: PO-008812
PC-IP15   received 1200 EA
CH-20W    received  600 EA      checked by: RT
```

**Invoice**

```
LUMEN ACCESSORIES LTD.   INVOICE  LA-77104   2026-11-01
Bill to: Caseworks Inc.   PO: PO-008812
PC-IP15  Clear phone case iPhone 15   1200 EA x 3.10 =  3,720.00
CH-20W   20W USB-C charger             600 EA x 6.85 =  4,110.00
Amount due USD 7,830.00   Terms Net 30
```

## PREVIEW-02 · messy · northside
**Answer key:** real discrepancy = False, reason = `none`, next step = `pay`, dollars at risk = $0.00, noise = date_format, number_format, uom_pack, po_ref_format, vendor_alias, handwritten_note, ocr_char_noise

**Purchase order**

```
NORTHSIDE HOSPITAL SUPPLY - PURCHASE ORDER
PO Number: PO-004471            Date: 2026-10-14
Supplier: MedLine Devices Inc.   Ship to: Central Warehouse, Dock 2
LN  SKU      DESCRIPTION                   QTY  UOM   UNIT PRICE    EXTENDED
1   INF-220  Infusion pump, dual channel     2  EA    40,000.00     80,000.00
2   TUB-05   IV tubing set                  50  EA        12.40        620.00
                                                     TOTAL USD    80,620.00
```

**Shipping notice**

```
MEDLINE DEVICES  ASN 88123   shipped 22 Oct 2026
ref P.O. 4471     carrier FastFreight  tracking FF-55102
INF-220 qty shipped 2
TUB-05  qty shipped 1 CS (50 EA)
```

**Goods receipt**

```
GOODS RECEIPT   Central WH   10/28/26
PO#: 4471     Supplier: Medline Devices
SKU      DESCRIPTION          QTY
INF-220  Infusion pump DC       2
TUB-05   IV tubing set         __    [handwritten: '1 cs = 50 ✓ JM']
```

**Invoice**

```
Medline Devices, Inc.        INVOICE INV-90217      Date 3 Nov 2026
Your ref: P.O. 4471            Bill to: Northside Hospital Supply
INF-220  Infusion Pump DC        2  @ 40.000,00     80.000,00
TUB-05   IV Tubing               1 CS (50 EA) @ 620,00    620,00
TOTAL DUE   USD 80.62O,00
```

**As scanned images:** [po](images/PREVIEW-02/po.png), [shipping_notice](images/PREVIEW-02/shipping_notice.png), [gr](images/PREVIEW-02/gr.png), [invoice](images/PREVIEW-02/invoice.png)

## PREVIEW-03 · real · northside
**Answer key:** real discrepancy = True, reason = `lost_in_transit`, next step = `claim_from_carrier`, dollars at risk = $124.00, noise = handwritten_note, number_format

**Purchase order**

```
NORTHSIDE HOSPITAL SUPPLY - PURCHASE ORDER
PO Number: PO-004502            Date: 2026-10-16
Supplier: MedLine Devices Inc.   Ship to: Central Warehouse, Dock 2
LN  SKU      DESCRIPTION                   QTY  UOM   UNIT PRICE    EXTENDED
1   INF-220  Infusion pump, dual channel     2  EA    40,000.00     80,000.00
2   TUB-05   IV tubing set                  50  EA        12.40        620.00
                                                     TOTAL USD    80,620.00
```

**Shipping notice**

```
MEDLINE DEVICES  ASN 88190   shipped 24 Oct 2026
ref P.O. 4502     carrier FastFreight
INF-220 qty shipped 2
TUB-05  qty shipped 50
```

**Goods receipt**

```
GOODS RECEIPT   Central WH   10/30/26
PO#: 4502
INF-220  Infusion pump DC       2
TUB-05   IV tubing set         __    [handwritten: 'rcvd 40, box crushed JM']
```

**Invoice**

```
Medline Devices, Inc.        INVOICE INV-90288      Date 4 Nov 2026
Your ref: P.O. 4502
INF-220  Infusion Pump DC        2  @ 40.000,00     80.000,00
TUB-05   IV Tubing              50  @ 12,40            620,00
TOTAL DUE   USD 80.620,00
```

## PREVIEW-04 · in_transit · caseworks
**Answer key:** real discrepancy = False, reason = `gr_missing_in_transit`, next step = `wait`, dollars at risk = $0.00, noise = none

**Purchase order**

```
CASEWORKS INC.  PURCHASE ORDER  PO-008840  2026-10-28
Vendor: Lumen Accessories Ltd.
SKU       Description               Qty   UOM  Unit    Amount
SP-GL15   Tempered glass protector  3000  EA   1.95    5,850.00
Total                                                  5,850.00
```

**Shipping notice**

```
ADVANCE SHIP NOTICE  ASN-55102  Lumen Accessories
Ref PO-008840   Ship date 2026-11-02   Carrier: CoastFreight   ETA 2026-11-07
SP-GL15  shipped 3000 EA
```

**Goods receipt**

```
(not present: goods not received yet)
```

**Invoice**

```
LUMEN ACCESSORIES LTD.   INVOICE  LA-77161   2026-11-03
PO: PO-008840
SP-GL15  Tempered glass protector  3000 EA x 1.95 = 5,850.00
Amount due USD 5,850.00
```
