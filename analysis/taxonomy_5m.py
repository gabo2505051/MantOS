"""
taxonomy_5m.py — Módulo de Clasificación de Causas de Falla por Metodología 5M
-----------------------------------------------------------------------------
Categoriza en memoria las descripciones de órdenes de trabajo (qmtxt / ltxtaufk)
en las 5M industriales:
  - MAQUINA: Falla física, mecánica, eléctrica, descalibración de instrumentos, avería de válvulas/sellos.
  - MANO_DE_OBRA: Error operacional, mal acople de componentes, mala manipulación de operador.
  - METODO: Receta fuera de parámetro, velocidad o ajuste de proceso fuera de especificación.
  - MATERIAL: Insumo defectuoso, materia prima/empaque fuera de especificación.
  - N_A: Mantenimiento preventivo programado (PM02) o rutina sin afectación/falla física.
"""

import re
from typing import Dict, Optional

# Diccionario de reglas por expresiones regulares
TAXONOMY_5M: Dict[str, Dict] = {
    # ── MÁQUINA (Deterioro / Falla Física / Instrumentación) ──────────────────
    "DESCALIBRACION_INSTRUMENTO": {
        "categoria_5m": "MAQUINA",
        "causa_simplificada": "Des-calibración de instrumento",
        "patterns": [
            r"\bdescalib\w*", r"\bcalib\w*", r"\bdrift\b", r"\bsensor\b",
            r"\btransmisor\b", r"\btermo-par\b", r"\btermopar\b", r"\bpresostato\b",
            r"\balarma de gases\b", r"\balarma gases\b", r"\balarma escarcha\b"
        ],
    },
    "AVERIA_EMPAQUES": {
        "categoria_5m": "MAQUINA",
        "causa_simplificada": "Avería de empaques / sellos",
        "patterns": [
            r"\bempaque\w*", r"\bsello\w*", r"\bo-ring\b", r"\boring\b",
            r"\bjunta\b", r"\bfuga\b", r"\breten\b", r"\bretener\b"
        ],
    },
    "AVERIA_VALVULA": {
        "categoria_5m": "MAQUINA",
        "causa_simplificada": "Avería de válvula / actuador",
        "patterns": [
            r"\bvalvula\w*", r"\bvlv\b", r"\bactuador\b", r"\bsolenoide\b",
            r"\bpiston\b", r"\bcilindro neum\w*"
        ],
    },
    "RODAMIENTO_DESGASTADO": {
        "categoria_5m": "MAQUINA",
        "causa_simplificada": "Desgaste de rodamientos / cojinetes",
        "patterns": [
            r"\brodamiento\w*", r"\brodaje\w*", r"\bcojinete\w*", r"\bvibracion\w*",
            r"\bruido mecanico\b", r"\bchumacera\b"
        ],
    },
    "FALLO_ELECTRICO_MOTOR": {
        "categoria_5m": "MAQUINA",
        "causa_simplificada": "Fallo de motor / sistema eléctrico",
        "patterns": [
            r"\bmotor\b", r"\bcorto\b", r"\bfusible\b", r"\brele\b", r"\bvariador\b",
            r"\bcontactor\b", r"\bsobrefrecuencia\b", r"\bsobrecalentamiento\b", r"\bresistencia\b"
        ],
    },

    # ── MANO DE OBRA (Operación / Manipulación / Configuración) ─────────────
    "MAL_ACOPLE_LAMINADOR": {
        "categoria_5m": "MANO DE OBRA",
        "causa_simplificada": "Mal acople de hoja / rodillo",
        "patterns": [
            r"\bacople\b", r"\bhoja\b", r"\blaminador\b", r"\bmal armado\b",
            r"\bdesalineacion manual\b", r"\brodillo rascador\b"
        ],
    },
    "ERROR_OPERATIVO": {
        "categoria_5m": "MANO DE OBRA",
        "causa_simplificada": "Error de operación / manipulación",
        "patterns": [
            r"\boperador\w*", r"\bmal uso\b", r"\batasco producto\b", r"\bparada manual\b",
            r"\bdesatencion\b", r"\badvertencia operador\b", r"\balimentacion incorrecta\b"
        ],
    },

    # ── METODO (Proceso / Parámetros) ─────────────────────────────────────────
    "DESAJUSTE_PARAMETRO": {
        "categoria_5m": "METODO",
        "causa_simplificada": "Desajuste de parámetro de proceso",
        "patterns": [
            r"\breceta\b", r"\bvelocidad excesiva\b", r"\btemperatura fuera de rango\b",
            r"\bpresion fuera de rango\b"
        ],
    },

    # ── MATERIAL (Insumos / Materia Prima) ────────────────────────────────────
    "DEFECTO_MATERIAL": {
        "categoria_5m": "MATERIAL",
        "causa_simplificada": "Material o insumo fuera de tolerancia",
        "patterns": [
            r"\bmasa defectuosa\b", r"\bfilm defectuoso\b", r"\bcarton fuera de medida\b",
            r"\bharina\b", r"\bmezcla\b"
        ],
    },

    # ── N/A (Mantenimiento Programado / Sin afectación) ───────────────────────
    "MANTENIMIENTO_PROGRAMADO": {
        "categoria_5m": "N/A",
        "causa_simplificada": "N/A (Mantenimiento Programado)",
        "patterns": [
            r"\bpreventivo\b", r"\bprev\b", r"\binspeccion\b", r"\brutina\b",
            r"\bplanificado\b", r"\bprogramado\b", r"\bcheck\b", r"\bsin novedad\b"
        ],
    },
}


def classify_cause_5m(
    qmtxt: Optional[str] = None,
    ltxtaufk: Optional[str] = None,
    auart: Optional[str] = None,
) -> Dict[str, str]:
    """
    Clasifica una OT según la metodología 5M y retorna su causa simplificada.

    Args:
        qmtxt: Texto corto del aviso o falla en SAP.
        ltxtaufk: Texto largo técnico adicional.
        auart: Clase de orden SAP ('PM01' correctivo, 'PM02' preventivo, 'PM03' operacional).

    Returns:
        Dict con keys: 'categoria_5m' y 'causa_simplificada'.
    """
    # Si es PM02 (Preventivo) y no especifica falla crítica, se considera N/A (Mantenimiento Programado)
    full_text = f"{qmtxt or ''} {ltxtaufk or ''}".strip()
    
    if auart == "PM02" and not any(kw in full_text.lower() for kw in ["fallo", "averia", "rotura", "urgente"]):
        return {
            "categoria_5m": "N/A",
            "causa_simplificada": "N/A (Mantenimiento Programado)"
        }

    if not full_text:
        if auart == "PM02":
            return {"categoria_5m": "N/A", "causa_simplificada": "N/A (Mantenimiento Programado)"}
        return {"categoria_5m": "OTRO", "causa_simplificada": "Sin Descripción Especificada"}

    text_lower = full_text.lower()

    # Evaluación por patrones regex
    for key, info in TAXONOMY_5M.items():
        for pat in info["patterns"]:
            if re.search(pat, text_lower):
                return {
                    "categoria_5m": info["categoria_5m"],
                    "causa_simplificada": info["causa_simplificada"]
                }

    # Fallback por omisión: si es PM01 (correctivo) se asume falla física de Máquina si no calzó en otro
    if auart == "PM01":
        return {
            "categoria_5m": "MAQUINA",
            "causa_simplificada": "Otras Averías Mecánicas"
        }

    return {
        "categoria_5m": "N/A",
        "causa_simplificada": "N/A (Actividad Operacional)"
    }

