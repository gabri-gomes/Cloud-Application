use std::io;

fn main() {
    println!("Por favor, introduz um número:");

    // Cria uma nova String para armazenar a entrada do utilizador
    let mut entrada = String::new();

    // Lê a entrada do utilizador da consola
    io::stdin()
        .read_line(&mut entrada)
        .expect("Falha ao ler a linha");

    // Converte a string para um número (i32)
    let numero: i32 = match entrada.trim().parse() {
        Ok(n) => n,
        Err(_) => {
            println!("Não foi introduzido um número válido.");
            return;
        }
    };

    println!("O número que introduziste foi: {}", numero);
}

