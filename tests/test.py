def main():
    try:
        numero = int(input("Por favor, introduz um número: "))
        print(f"O número que introduziste foi: {numero}")
    except ValueError:
        print("Não foi introduzido um número válido.")

if __name__ == "__main__":
    main()
