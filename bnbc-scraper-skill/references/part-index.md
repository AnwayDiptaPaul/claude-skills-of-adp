# BNBC 2020 Part / chapter index

Route by domain first, then retrieve. Inside a Part, the first segment of a clause id is its chapter number (Part 6, Chapter 2 -> `2.x.x`).

| Part | Directory | Use for |
|---|---|---|
| 1 | `Part_01_Scope_and_Definitions` | definitions, scope, abbreviations, units |
| 2 | `Part_02_Administration_and_Enforcement` | permits, inspection, enforcement authority, penalties |
| 3 | `Part_03_General_Building_Requirements` | occupancy classes, construction types, space/height/setback rules, energy efficiency |
| 4 | `Part_04_Fire_Protection` | fire precautions, means of egress, detection, sprinklers, extinguishers |
| 5 | `Part_05_Building_Materials` | material quality standards (cement, steel, masonry, timber, concrete) |
| 6 | `Part_06_Structural_Design` | ALL structural design: loads, seismic, wind, foundations, RC, steel, masonry, timber, bamboo, prestressed, ferrocement, composite |
| 7 | `Part_07_Construction_Practices_and_Safety` | construction management, site safety, scaffolding, quality control |
| 8 | `Part_08_Building_Services` | electrical, HVAC, plumbing and drainage, gas, lifts and escalators |
| 9 | `Part_09_Alteration_and_Addition` | alteration, addition, evaluation of existing buildings, conservation |
| 10 | `Part_10_Signs_and_Outdoor_Display` | signs, billboards, outdoor display |

## Chapters and clause counts (from CLAUSE_ROUTER.md)

### Part 1
- Ch 1: Title, Purpose, Scope, Etc (5 clauses)
- Ch 2: Definitions (1 clauses)
- Ch 3: Abbreviations (1 clauses)
### Part 2
- Ch 1: Purpose and Applicability (2 clauses)
- Ch 2: Establishment of Authority, Etc (19 clauses)
- Ch 3: Permits and Inspections (7 clauses)
### Part 3
- Ch 1: General Building Requirements (80 clauses)
- Ch 2: Classification of Buildings Based on Occupancy (73 clauses)
- Ch 3: Classification of Building Construction Types Based on Fire Resistance (14 clauses)
- Ch 4: Energy Efficiency and Sustainability (33 clauses)
### Part 4
- Ch 1: Precautionary Requirements (4 clauses)
- Ch 2: Means of Egress (18 clauses)
- Ch 3: Equipment and In-Built Facilities Standards (47 clauses)
### Part 5
- Ch 1: Building Materials (33 clauses)
### Part 6
- Ch 1: Definitions and General Requirements (48 clauses)
- Ch 2: Loads on Buildings and Structures (128 clauses)
- Ch 3: Soils and Foundations (115 clauses)
- Ch 4: Bamboo Structures (47 clauses)
- Ch 5: Strength Design of Reinforced Concrete Structures (332 clauses)
- Ch 6: Masonry Structures (58 clauses)
- Ch 7: Detailing of Reinforcement in Concrete Structures (79 clauses)
- Ch 8: Prestressed Concrete Structures (119 clauses)
- Ch 9: Steel Structures (340 clauses)
- Ch 10: Timber Structures (131 clauses)
- Ch 11: Ferrocement Structures (63 clauses)
- Ch 12: Steel-Concrete Composite Structural Members (64 clauses)
### Part 7
- Ch 1: Construction Management, Inspection, Quality Control and Safety (2 clauses)
### Part 8
- Ch 1: Electrical and Electronic Engineering (70 clauses)
- Ch 2: Air-Conditioning, Heating and Ventilation (155 clauses)
- Ch 3: Plumbing and Drainage (107 clauses)
- Ch 4: Gas Supply (165 clauses)
- Ch 5: Lifts and Escalators (43 clauses)
### Part 9
- Ch 1: Applicability and Implementation (18 clauses)
- Ch 2: Evaluation and Compliance (28 clauses)
- Ch 3: Conservation (17 clauses)
### Part 10
- Ch 1: Scope and General (34 clauses)
- Ch 2: General Requirements (13 clauses)
- Ch 3: Specific Requirements for Various Types of Signs (51 clauses)

## Part 6 landmarks (verified present in the repo)

- Storey drift limitation 1.5.6.1; sway limitation 1.5.6.2
- Seismic zoning 2.5.4.2; design response spectrum 2.5.4.3; seismic design category 2.5.5.2
- Design base shear 2.5.7.1; building period 2.5.7.2; seismic weight 2.5.7.3; storey drift 2.5.7.7; drift and deformation 2.5.14
- Piles 3.10.x; pile load tests 3.11.x

Chapter numbers above follow router order; confirm with `toc --part 6 --chapter <name>` before citing a chapter number.
