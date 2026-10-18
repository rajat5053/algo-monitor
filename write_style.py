with open('quant_preview_src/App.css', 'r', encoding='utf-8') as f:
    text = f.read()

start_marker = '___CSS_LOADER_EXPORT___.push([module.id, `'
end_marker = '`, "",'
p1 = text.find(start_marker)
if p1 != -1:
    p1 += len(start_marker)
    p2 = text.find(end_marker, p1)
    css_content = text[p1:p2]
    with open('algo_monitor/dashboard/static/style.css', 'w', encoding='utf-8') as out:
        out.write('/* Algo Monitor Quant Terminal v3 CSS */\n' + css_content)
    print('Wrote style.css, length:', len(css_content))
else:
    print('Start marker not found!')
