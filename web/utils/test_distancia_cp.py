from calcula_KM_con_CP import calcula_KM_con_CP

def main():
    ejemplos = [
        ("28320", "Pinto", "28231", "Las Rozas"),
        ("04070", "", "04118", "San Jose"),
        ("28001", "Madrid", "08001", "Barcelona"),
    ]

    for cp1, loc1, cp2, loc2 in ejemplos:
        dist = calcula_KM_con_CP(cp1, loc1, cp2, loc2)
        if dist is None:
            print(f"No se pudo calcular: {cp1}-{loc1} vs {cp2}-{loc2}")
        else:
            print(f"{cp1} ({loc1 or 'default'}) – {cp2} ({loc2 or 'default'}): {dist:.2f} km")

if __name__ == "__main__":
    main()