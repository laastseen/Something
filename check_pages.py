import os

def estimate_pages():
    files = ['part1.md', 'part2.md', 'appendix.md']
    total_chars = 0
    for f in files:
        if os.path.exists(f):
            with open(f, 'r', encoding='utf-8') as file:
                content = file.read()
                # Удаляем маркдаун разметку для более точного счета текста
                clean_text = content.replace('#', '').replace('```', '').replace('**', '')
                total_chars += len(clean_text)
    
    # Стандартная страница (ГОСТ) - это примерно 1800 знаков с пробелами
    # С учетом 1.5 интервала и полей 3см/1.5см, в Ворде получается 
    # примерно 1500-1800 знаков на страницу.
    pages = total_chars / 1800
    return total_chars, pages

if __name__ == "__main__":
    chars, pages = estimate_pages()
    print(f"Общее количество знаков: {chars}")
    print(f"Приблизительное количество страниц (1800 зн/стр): {pages:.2f}")
    
    if pages < 40:
        print(f"Нужно еще минимум {40 - pages:.2f} страниц.")
    else:
        print("Цель в 40 страниц достигнута!")
