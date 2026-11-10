// Meta Business Suite → Insights → Conteúdo (business.facebook.com/latest/insights/content).
// Cole no javascript_tool, na aba já aberta nessa página. Rola a grade até o fim para carregar todas as
// linhas e devolve quantas existem. Depois disso, leia tudo de uma vez com get_page_text.
// Só lê: não clica em nada.
await (async () => {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const first = document.querySelector('[role=row] [role=gridcell]');
  if (!first) return 'Tabela não encontrada: abra Insights → Conteúdo e espere carregar.';
  let box = first;
  while (box && !(box.scrollHeight > box.clientHeight + 20 && /(auto|scroll)/.test(getComputedStyle(box).overflowY))) box = box.parentElement;
  const count = () => document.querySelectorAll('[role=row]').length - 1;
  let last = -1, stable = 0;
  for (let i = 0; i < 300 && stable < 5; i++) {
    (box || document.scrollingElement).scrollTop += 1200;
    window.scrollBy(0, 1200);
    await sleep(800);
    const c = count();
    stable = c === last ? stable + 1 : 0;
    last = c;
  }
  (box || document.scrollingElement).scrollTop = 0;
  return `${count()} linhas carregadas na tabela`;
})();
