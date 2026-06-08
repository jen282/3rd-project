import re
import os


def extract_tables_and_text(md_file_path, output_dir, extra_chars=None):
    with open(md_file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    table_dir = os.path.join(output_dir, 'table')
    txt_dir = os.path.join(output_dir, 'txt')
    os.makedirs(table_dir, exist_ok=True)
    os.makedirs(txt_dir, exist_ok=True)

    # Extract tables
    table_pattern = re.compile(r'<table>.*?</table>', re.DOTALL)
    tables = table_pattern.findall(content)
    for i, table in enumerate(tables, 1):
        table_file = os.path.join(table_dir, f'table_{i}.html')
        with open(table_file, 'w', encoding='utf-8') as f:
            f.write(table)
    print(f"  tables: {len(tables)}개 → {table_dir}")

    # Extract body text
    text = content

    # Remove table blocks
    text = table_pattern.sub('', text)
    # Remove figure blocks
    text = re.sub(r'<figure>.*?</figure>', '', text, flags=re.DOTALL)
    # Remove HTML comments (<!-- ... -->)
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    # Remove block math ($$...$$)
    text = re.sub(r'\$\$.*?\$\$', '', text, flags=re.DOTALL)
    # Remove inline math ($...$)
    text = re.sub(r'\$[^$\n]+?\$', '', text)
    # Strip markdown heading markers (keep text)
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    # Remove bullet point markers (•, ·) but keep the text
    text = re.sub(r'^[•·]\s*', '', text, flags=re.MULTILINE)
    # Remove extra characters specific to certain sources (e.g. | for scan OCR artifacts)
    if extra_chars:
        pattern = '[' + re.escape(''.join(extra_chars)) + ']'
        text = re.sub(pattern, '', text)
    # Collapse multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    txt_file = os.path.join(txt_dir, 'content.txt')
    with open(txt_file, 'w', encoding='utf-8') as f:
        f.write(text)
    print(f"  text   → {txt_file}")


if __name__ == '__main__':
    base_dir = os.path.dirname(os.path.abspath(__file__))

    targets = ['result-digital', 'result-scan']
    for folder in targets:
        md_path = os.path.join(base_dir, folder, 'content.md')
        if not os.path.exists(md_path):
            print(f"[SKIP] {md_path} 없음")
            continue
        print(f"\n[{folder}]")
        extra = ['|', '·'] if folder == 'result-scan' else None
        extract_tables_and_text(md_path, os.path.join(base_dir, folder), extra_chars=extra)

    print("\n완료.")
