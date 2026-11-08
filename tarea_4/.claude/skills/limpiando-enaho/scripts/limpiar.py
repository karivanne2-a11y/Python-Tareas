"""Limpia la ENAHO 2024 (módulos 34 y 02) y valida el resultado.

    uv run .claude/skills/limpiando-enaho/scripts/limpiar.py --anio 2024

Entra : datos/966-Modulo34.zip y datos/966-Modulo02.zip (o los .dta ya extraídos en datos/)
Sale  : salidas/personas_2024.parquet, salidas/indicadores.csv, salidas/validacion.txt

Si falla una validación ESENCIAL el script termina con código 1, escribe validacion.txt con las FALLIDAS y
NO guarda la base. Nunca ajusta los resultados para que coincidan con la referencia.
"""
import argparse
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd

REF = {"pobreza": 27.6, "urbana": 24.8, "rural": 39.3, "residentes": 108_664, "hogares": 33_691}
TOL = 0.1  # puntos porcentuales
DEPARTAMENTOS = {
    "01": "Amazonas", "02": "Áncash", "03": "Apurímac", "04": "Arequipa", "05": "Ayacucho", "06": "Cajamarca",
    "07": "Callao", "08": "Cusco", "09": "Huancavelica", "10": "Huánuco", "11": "Ica", "12": "Junín",
    "13": "La Libertad", "14": "Lambayeque", "15": "Lima", "16": "Loreto", "17": "Madre de Dios",
    "18": "Moquegua", "19": "Pasco", "20": "Piura", "21": "Puno", "22": "San Martín", "23": "Tacna",
    "24": "Tumbes", "25": "Ucayali"}
ANCHOS = {"conglome": 6, "vivienda": 3, "hogar": 2, "codperso": 2, "ubigeo": 6}


def buscar_dta(datos: Path, modulo: str, anio: int) -> Path:
    """Devuelve el .dta del módulo ('34' sumaria o '02' miembros); descomprime el zip si hace falta."""
    zip_ = next(iter(datos.glob(f"*Modulo{modulo}.zip")), None)
    if zip_ is not None:
        destino = datos / f"extraido_modulo{modulo}"
        if not destino.exists():
            with zipfile.ZipFile(zip_) as z:
                z.extractall(destino)
    candidatos = [p for p in datos.rglob("*.dta")]
    if modulo == "34":
        ok = [p for p in candidatos if re.fullmatch(rf"sumaria-{anio}\.dta", p.name.lower())]
    else:
        ok = [p for p in candidatos if re.fullmatch(rf"enaho01-{anio}-200\.dta", p.name.lower())]
    if not ok:
        sys.exit(f"ERROR: no encuentro el módulo {modulo} en {datos}. Bajen los zip del INEI (ver README) a esa carpeta.")
    return ok[0]


def llaves_texto(df: pd.DataFrame) -> pd.DataFrame:
    """Las llaves y el ubigeo como texto de ancho fijo: así no se pierden los ceros iniciales."""
    for col, ancho in ANCHOS.items():
        if col in df.columns:
            s = df[col].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
            df[col] = s.str.zfill(ancho)
    return df


def leer(path: Path) -> pd.DataFrame:
    df = pd.read_stata(path, convert_categoricals=False)
    df.columns = [c.lower() for c in df.columns]  # la columna del año llega como "aÑo"
    return llaves_texto(df)


def pct(pobre, peso) -> float:
    return float((pobre * peso).sum() / peso.sum() * 100)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--anio", type=int, default=2024)
    ap.add_argument("--datos", default="datos")
    ap.add_argument("--salidas", default="salidas")
    a = ap.parse_args()
    datos, salidas = Path(a.datos), Path(a.salidas)
    salidas.mkdir(exist_ok=True)

    suma = leer(buscar_dta(datos, "34", a.anio))
    pers = leer(buscar_dta(datos, "02", a.anio))
    k_h = ["conglome", "vivienda", "hogar"]
    k_p = k_h + ["codperso"]
    n_modulo02 = len(pers)

    # 3. residentes habituales
    for c in ("p204", "p205", "p206"):
        pers[c] = pd.to_numeric(pers[c], errors="coerce")
    res = pers[((pers.p204 == 1) & (pers.p205 == 2)) | ((pers.p204 == 2) & (pers.p206 == 1))].copy()

    # 4. unir personas (m) con hogares (1)
    h_cols = k_h + [c for c in ("ubigeo", "dominio", "estrato", "pobreza", "factor07", "mieperho") if c in suma.columns]
    p_cols = k_p + [c for c in ("p203", "p207", "p208a", "facpob07") if c in res.columns]
    base = res[p_cols].merge(suma[h_cols], on=k_h, how="left", validate="m:1", indicator=True)
    sin_hogar = int((base["_merge"] != "both").sum())
    base = base.drop(columns="_merge")

    # 5. variables derivadas
    base["departamento"] = base.ubigeo.str[:2]
    base["estrato"] = pd.to_numeric(base.estrato, errors="coerce")
    base["urbano"] = base.estrato <= 5
    base["area"] = base.urbano.map({True: "Urbana", False: "Rural"})
    base["pobreza"] = pd.to_numeric(base.pobreza, errors="coerce")
    base["pobre"] = (base.pobreza <= 2).astype(int)
    base["pobre_extremo"] = (base.pobreza == 1).astype(int)
    base["sexo"] = pd.to_numeric(base.get("p207"), errors="coerce").map({1: "Hombre", 2: "Mujer"})
    base["edad"] = pd.to_numeric(base.get("p208a"), errors="coerce")

    # 6. validaciones. (nombre, esencial, cumple, detalle)
    v = []
    suma_pob = pd.to_numeric(suma.pobreza, errors="coerce")
    w_h = pd.to_numeric(suma.factor07) * pd.to_numeric(suma.mieperho)
    nac_suma = pct((suma_pob <= 2).astype(int), w_h)
    nac_pers = pct(base.pobre, base.facpob07)
    u = suma.assign(p=(suma_pob <= 2).astype(int), w=w_h, urb=pd.to_numeric(suma.estrato) <= 5)
    urb_s, rur_s = pct(u[u.urb].p, u[u.urb].w), pct(u[~u.urb].p, u[~u.urb].w)

    v.append(("Hogares en la sumaria", False, len(suma) == REF["hogares"], f"{len(suma):,} (referencia {REF['hogares']:,})"))
    v.append(("Llaves de hogar únicas en la sumaria", True, not suma.duplicated(k_h).any(), "conglome, vivienda, hogar"))
    v.append(("Llaves de persona únicas en el módulo 02", True, not pers.duplicated(k_p).any(), "conglome, vivienda, hogar, codperso"))
    v.append(("Llaves como texto con ceros iniciales", True,
              bool((suma.conglome.str.len() == 6).all() and (suma.vivienda.str.len() == 3).all()
                   and (suma.hogar.str.len() == 2).all() and (base.ubigeo.str.len() == 6).all()),
              "conglome(6), vivienda(3), hogar(2), ubigeo(6)"))
    if a.anio == 2024:
        v.append(("Residentes habituales", True, len(res) == REF["residentes"],
                  f"{len(res):,} de {n_modulo02:,} filas del módulo 02 (referencia {REF['residentes']:,})"))
    v.append(("Unión m:1 sin perder ni duplicar personas", True, len(base) == len(res) and sin_hogar == 0,
              f"{len(res):,} personas antes, {len(base):,} después, {sin_hogar} sin hogar en la sumaria"))
    codigos = set(base.departamento.unique())
    v.append(("25 códigos territoriales (01 a 25; Lima 15 y Callao 07 separados)", True,
              codigos == set(DEPARTAMENTOS), f"{len(codigos)} códigos distintos"))
    if a.anio == 2024:
        v.append(("Pobreza nacional (sumaria, factor07 × mieperho) = 27.6 ± 0.1", True,
                  abs(nac_suma - REF["pobreza"]) <= TOL, f"{nac_suma:.2f} %"))
        v.append(("Pobreza nacional (personas, facpob07) = 27.6 ± 0.1", True,
                  abs(nac_pers - REF["pobreza"]) <= TOL, f"{nac_pers:.2f} %"))
        v.append(("Pobreza urbana (sumaria) = 24.8 ± 0.1", True, abs(urb_s - REF["urbana"]) <= TOL, f"{urb_s:.2f} %"))
        v.append(("Pobreza rural (sumaria) = 39.3 ± 0.1", True, abs(rur_s - REF["rural"]) <= TOL, f"{rur_s:.2f} %"))
    simple = float(base.pobre.mean() * 100)
    v.append(("La ponderación importa (el promedio simple no sirve)", False, abs(simple - nac_pers) > 0.5,
              f"promedio simple {simple:.2f} % frente a {nac_pers:.2f} % ponderado"))

    lineas = [f"VALIDACIÓN ENAHO {a.anio}", "=" * 60]
    for nombre, esencial, ok, det in v:
        lineas.append(f"[{'APROBADA' if ok else 'FALLIDA '}]{' (esencial)' if esencial else ''} {nombre}: {det}")
    fallas = [n for n, e, ok, _ in v if e and not ok]
    lineas += ["=" * 60, "RESULTADO: " + ("APROBADO" if not fallas else f"FALLIDO ({len(fallas)} validaciones esenciales)")]
    (salidas / "validacion.txt").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print("\n".join(lineas))
    if fallas:
        sys.exit("ERROR: falló una validación esencial; no se guarda la base. Revisen salidas/validacion.txt.")

    # 7. guardar
    cols = k_p + ["ubigeo", "departamento", "dominio", "estrato", "urbano", "area", "sexo", "edad",
                  "pobreza", "pobre", "pobre_extremo", "facpob07", "factor07", "mieperho"]
    base[[c for c in cols if c in base.columns]].to_parquet(salidas / f"personas_{a.anio}.parquet", index=False)

    # Nacional, área y departamento: método del INEI (hogares, factor07 × mieperho), que reproduce la referencia de
    # la Sesión 16 con diferencia máxima de 0.05 pp. Sexo necesita personas: facpob07.
    hog = base.drop_duplicates(k_h).assign(w=lambda d: d.factor07 * d.mieperho)
    filas = [("nacional", "PE", "Perú", "hogares", pct(hog.pobre, hog.w), pct(hog.pobre_extremo, hog.w), hog.w.sum(), len(hog))]
    for nivel, col in (("area", "area"), ("departamento", "departamento")):
        for clave, g in hog.groupby(col):
            nombre = DEPARTAMENTOS[clave] if nivel == "departamento" else clave
            filas.append((nivel, clave, nombre, "hogares", pct(g.pobre, g.w), pct(g.pobre_extremo, g.w), g.w.sum(), len(g)))
    for clave, g in base.dropna(subset=["sexo"]).groupby("sexo"):
        filas.append(("sexo", clave, clave, "personas", pct(g.pobre, g.facpob07), pct(g.pobre_extremo, g.facpob07),
                      g.facpob07.sum(), len(g)))
    ind = pd.DataFrame(filas, columns=["nivel", "codigo", "nombre", "metodo", "pobreza_pct", "pobreza_extrema_pct", "poblacion", "n_muestra"])
    ind["poblacion"] = ind.poblacion.round().astype("int64")  # evita la notación científica en el CSV
    ind.round({"pobreza_pct": 2, "pobreza_extrema_pct": 2}).to_csv(salidas / "indicadores.csv", index=False)
    print(f"Guardados: personas_{a.anio}.parquet, indicadores.csv ({len(ind)} filas)")


if __name__ == "__main__":
    main()
