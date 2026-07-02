# Catálogo Técnico — Estructura de Planta SAP PM (Simulada)

> Referencia para interpretar el archivo `sap_raw_export.csv`.
> Simula la estructura que escupiría una API OData o extracción directa de SAP (tablas AUFK, AFIH, ILOA, EQUI).

---

## 1. Mapeo de Columnas (Original → SAP)

| Columna Original | Campo SAP | Tabla | Descripción |
|---|---|---|---|
| `OT` | `AUFNR` | AUFK | Número de orden de trabajo (7 dígitos, serie 4xxxxxx) |
| `Aviso` | `QMNUM` | QMIH | Número de aviso de mantenimiento (8 dígitos, serie 2xxxxxxx) |
| `Fecha_Inicio` | `GSTRP` | AUFK | Fecha inicio extrema planificada (ISO: `YYYY-MM-DDTHH:MM:SSZ`) |
| `Fecha_Fin` | `GLTRP` | AUFK | Fecha fin extrema planificada (ISO: `YYYY-MM-DDTHH:MM:SSZ`) |
| `Linea` + `Equipo` | `TPLNR` | ILOA | Ubicación técnica funcional (Functional Location) |
| `Equipo` | `EQUNR` | EQUI | ID de equipo (8 dígitos, serie 1000xxxx) |
| `Titulo_Falla` | `QMTXT` | QMEL | Texto corto del aviso (con errores tipográficos simulados) |
| `Descripcion_Tecnica` | `LTXTAUFK` | AUFK | Texto largo de la orden (con variaciones de calidad) |
| `Tipo_Mantenimiento` | `AUART` | AUFK | Clase de orden (PM01/PM02/PM03) |
| `Puesto_Trabajo` | `ARBPL` | CRHD | Centro de trabajo / puesto de trabajo |
| `Responsable` | `ERNAM` | AUFK | Usuario creador del registro |

---

## 2. Ubicaciones Técnicas (Functional Locations — TPLNR)

### Estructura Jerárquica

```
PGS                          ← Planta Galletera Sur (nivel 1)
└── PR                       ← Área: Producción (nivel 2)
    ├── LA1                  ← Línea 1: Galletas soda (nivel 3)
    │   ├── HRN01            ← Horno
    │   ├── SFR01            ← Sala de fermentado
    │   ├── LAM01            ← Laminador - Cortador
    │   ├── MES01            ← Mesa de trabajo
    │   ├── CEN01            ← Cintas de enfriamiento
    │   ├── ENV01            ← Envasadora (compartida)
    │   ├── ELV01            ← Elevador
    │   └── RPL01            ← Robot paletizador
    │
    ├── LA2                  ← Línea 2: Galleta tipo oblea
    │   ├── HRL01            ← Horno tipo Libro
    │   ├── CRM01            ← Cremadora
    │   ├── CRT01            ← Cortadora
    │   ├── CKC01            ← Cookie Capper
    │   ├── TF101            ← Túnel de frío N°1
    │   ├── TF201            ← Túnel de frío N°2
    │   ├── ARC01            ← Arcoenfriador
    │   ├── ENV01            ← Envasado
    │   └── RPL01            ← Robot paletizador
    │
    ├── LA3                  ← Línea 3 (sin producto específico)
    │   ├── EXT01            ← Extrusores
    │   ├── ELB01            ← Elaboración
    │   ├── MZC01            ← Mezclador 1 - 2
    │   ├── TDF01            ← Túnel de frío
    │   ├── BAN01            ← Bañadora
    │   ├── CRT01            ← Cortadora
    │   ├── DST01            ← Distribuidora
    │   └── RPL01            ← Robot paletizador
    │
    ├── LA4                  ← Línea 4: Alfajores ⭐ (línea principal)
    │   ├── BAN01            ← Bañadora
    │   ├── BUF01            ← Buffer
    │   ├── ENV01            ← Envasadora
    │   ├── INY01            ← Inyectora - Formadora
    │   ├── TDF01            ← Túnel de frío
    │   └── RPL01            ← Robot paletizador
    │
    └── LA5                  ← Línea 5: Galleta exportada
        ├── PRE01            ← Preparación
        ├── ENV01            ← Envasado
        ├── REM01            ← Robot empaquetador
        ├── ELV01            ← Elevador
        └── AGR01            ← Agrupado
```

### Tabla de Ubicaciones Técnicas Completa

| TPLNR | Línea | Equipo | EQUNR |
|---|---|---|---|
| `PGS-PR-LA1-HRN01` | Línea 1 - Galletas soda | Horno | 10001001 |
| `PGS-PR-LA1-SFR01` | Línea 1 - Galletas soda | Sala fermentado | 10001002 |
| `PGS-PR-LA1-LAM01` | Línea 1 - Galletas soda | Laminador - Cortador | 10001003 |
| `PGS-PR-LA1-MES01` | Línea 1 - Galletas soda | Mesa de trabajo | 10001004 |
| `PGS-PR-LA2-HRL01` | Línea 2 - Oblea | Horno tipo Libro | 10002001 |
| `PGS-PR-LA2-CRM01` | Línea 2 - Oblea | Cremadora | 10002002 |
| `PGS-PR-LA2-CRT01` | Línea 2 - Oblea | Cortadora | 10002003 |
| `PGS-PR-LA2-CKC01` | Línea 2 - Oblea | Cookie Capper | 10002004 |
| `PGS-PR-LA2-TF101` | Línea 2 - Oblea | Túnel de frío N°1 | 10002005 |
| `PGS-PR-LA2-TF201` | Línea 2 - Oblea | Túnel de frío N°2 | 10002006 |
| `PGS-PR-LA2-ARC01` | Línea 2 - Oblea | Arcoenfriador | 10002007 |
| `PGS-PR-LA3-EXT01` | Línea 3 | Extrusores | 10003001 |
| `PGS-PR-LA3-ELB01` | Línea 3 | Elaboración | 10003002 |
| `PGS-PR-LA3-MZC01` | Línea 3 | Mezclador 1 - 2 | 10003003 |
| `PGS-PR-LA4-BAN01` | Línea 4 - Alfajores | Bañadora | 10004001 |
| `PGS-PR-LA4-BUF01` | Línea 4 - Alfajores | Buffer | 10004002 |
| `PGS-PR-LA4-ENV01` | Línea 4 - Alfajores | Envasadora | 10004003 |
| `PGS-PR-LA4-INY01` | Línea 4 - Alfajores | Inyectora - Formadora | 10004004 |
| `PGS-PR-LA4-TDF01` | Línea 4 - Alfajores | Túnel de frío | 10004005 |
| `PGS-PR-LA4-RPL01` | Línea 4 - Alfajores | Robot paletizador | 10004006 |
| `PGS-PR-LA5-PRE01` | Línea 5 - Galleta export. | Preparación | 10005001 |
| `PGS-PR-LA5-ENV01` | Línea 5 - Galleta export. | Envasado | 10005002 |
| `PGS-PR-LA5-REM01` | Línea 5 - Galleta export. | Robot empaquetador | 10005003 |
| `PGS-PR-LA5-ELV01` | Línea 5 - Galleta export. | Elevador | 10005004 |
| `PGS-PR-LA5-AGR01` | Línea 5 - Galleta export. | Agrupado | 10009003 |
| `PGS-PR-LAX-DST01` | Compartido | Distribuidora | 10009001 |
| `PGS-PR-LAX-CEN01` | Compartido | Cintas enfriamiento | 10009002 |

---

## 3. Clases de Orden (AUART)

| Código | Nombre SAP | Equivalente Original | Descripción |
|---|---|---|---|
| `PM01` | Correctivo | Correctivo | Fallas no planificadas, requieren intervención inmediata |
| `PM02` | Preventivo | Preventivo | Mantenimiento programado: inspecciones, cambios, calibraciones |
| `PM03` | Operacional | Operacional | Micro-paros, atascos, reinicios — resueltos por operador/sistema |

### Distribución en el Dataset

| AUART | Registros | % |
|---|---|---|
| PM03 | 1,782 | 82.9% |
| PM02 | 300 | 14.0% |
| PM01 | 67 | 3.1% |

---

## 4. Centros de Trabajo (ARBPL)

| Centro | Tipo | Aplica a |
|---|---|---|
| `MEC-CORR` | Mecánica correctiva | PM01 |
| `ELE-CORR` | Eléctrica correctiva | PM01 |
| `TURNO-A` | Turno A | PM01 |
| `TURNO-B` | Turno B | PM01 |
| `TURNO-C` | Turno C | PM01 |
| `MEC-PREV` | Mecánica preventiva | PM02 |
| `ELE-PREV` | Eléctrica preventiva | PM02 |
| `INSP-GEN` | Inspección general | PM02 |
| `OPR-TURNO` | Operador de turno | PM03 |
| `SUP-LINEA` | Supervisor de línea | PM03 |

---

## 5. Usuarios del Sistema (ERNAM)

### Usuarios Humanos

| ID | Tipo | Aplica a |
|---|---|---|
| `JCASTRO` | Mecánico | PM01, PM02 |
| `MEC_01` | Mecánico | PM01, PM02 |
| `MEC_02` | Mecánico | PM01, PM02 |
| `MEC_03` | Mecánico | PM01, PM02 |
| `LGOMEZ` | Mecánico | PM01, PM02 |
| `RPEREZ` | Mecánico | PM01, PM02 |
| `AMARTINEZ` | Mecánico | PM01, PM02 |
| `FDIAZ` | Mecánico | PM01, PM02 |
| `MRODRIG` | Mecánico | PM01, PM02 |
| `PLOPEZ` | Mecánico | PM01, PM02 |

### Usuarios de Sistema

| ID | Descripción | Aplica a |
|---|---|---|
| `SYS_IIOT` | Sistema IIoT (sensores/PLC) | PM03, PM02 |
| `BAT_USER` | Usuario batch/programado | PM03, PM02 |
| `SYS_SCADA` | Sistema SCADA | PM03 |
| `RFC_PM` | Interfaz RFC de SAP PM | PM03, PM02 |

### Operadores

| ID | Descripción | Aplica a |
|---|---|---|
| `OPR_T1` | Operador Turno 1 | PM03 |
| `OPR_T2` | Operador Turno 2 | PM03 |
| `OPR_T3` | Operador Turno 3 | PM03 |
| `SUP_LINEA` | Supervisor de línea | PM03 |

---

## 6. Anomalías Inyectadas (Realismo)

### Paros Fantasma (GSTRP == GLTRP)
- **~10% de los registros** (214 de 2149) tienen `Fecha_Inicio = Fecha_Fin`
- Simula: mecánico que cerró la OT días después metiendo la misma fecha, o micro-paros que no se midieron correctamente

### Textos Sucios (QMTXT / LTXTAUFK)
- **Errores tipográficos**: "inspeccion" en vez de "inspección", "Se realizo" en vez de "Se realizó"
- **Abreviaciones**: "ATSC PRODUCTO", "m.paro oper", "RST CICLO", "MTO PREV."
- **Mayúsculas aleatorias**: ~20% de descripciones en MAYÚSCULAS completas
- **Truncados (~30%)**: "ok", "idem anterior", "sin observaciones", "equipo normalizado"

### Variantes de Nombres de Equipo
- "Robot paletizador", "Robot Paletizador", "Paletizador (Robot)" → todos mapean a `10004006`

---

## 7. Estadísticas del Dataset

| Métrica | Valor |
|---|---|
| Total registros | 2,149 |
| Rango temporal | Abril 2024 — Marzo 2026 |
| Líneas de producción | 5 |
| Equipos únicos | 29 |
| Ubicaciones técnicas | 27 |
| Paros fantasma | 214 (10%) |
| Usuarios únicos | 18 |

### Top 10 Ubicaciones por Frecuencia

| TPLNR | Equipo | Registros |
|---|---|---|
| PGS-PR-LA4-RPL01 | Robot paletizador | 334 |
| PGS-PR-LA4-INY01 | Inyectora - Formadora | 309 |
| PGS-PR-LA4-ENV01 | Envasadora | 308 |
| PGS-PR-LA4-BUF01 | Buffer | 305 |
| PGS-PR-LA4-TDF01 | Túnel de frío | 293 |
| PGS-PR-LA4-BAN01 | Bañadora | 291 |
| PGS-PR-LA1-HRN01 | Horno | 50 |
| PGS-PR-LA3-TDF01 | Túnel de frío (L3) | 29 |
| PGS-PR-LA5-REM01 | Robot empaquetador | 14 |
| PGS-PR-LA3-BAN01 | Bañadora (L3) | 13 |
