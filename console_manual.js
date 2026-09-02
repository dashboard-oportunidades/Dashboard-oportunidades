// Recolha manual de outlet — cola isto na Consola do browser (F12) enquanto
// vês a pagina do outlet numa loja, no Chrome normal (nunca e bloqueado,
// porque e navegacao humana a serio). Depois:
//   python ingerir_manual.py <ficheiro.json>
// com o resultado copiado guardado num ficheiro.
//
// Link do outlet de bases de duche:
// https://www.leroymerlin.pt/produtos/promocoes/outlet/?filters=%7B%22breadcrumb-1-label%22%3A%22Casas%2520de%2520banho%22%2C%22attribute-22088%22%3A%22Base%2520de%2520duche%22%7D
//
// Le o <script class="dataTms"> de cada produto -- dados estruturados que o
// proprio site usa para analitica, exatos e sem ambiguidade.

(function () {
  const found = {};
  // So dentro de #guidance-product-list -- a seccao "Ultimos produtos
  // vistos" mais abaixo na pagina usa a mesma estrutura dataTms, mas para
  // produtos vistos anteriormente (nada a ver com o outlet desta loja).
  const container = document.getElementById('guidance-product-list');
  const scripts = container ? container.querySelectorAll('script.dataTms') : [];
  scripts.forEach((script) => {
    let blocos;
    try {
      blocos = JSON.parse(script.textContent);
    } catch (e) {
      return;
    }
    blocos.forEach((bloco) => {
      if (bloco.name !== 'cdl_products_list') return;
      (bloco.value || []).forEach((produto) => {
        const pid = produto.identifier;
        const offer = produto.offer || {};
        const precoFinal = offer.unitprice_ati;
        if (!pid || precoFinal == null) return;
        const url =
          produto.url && produto.url.startsWith('/')
            ? location.origin + produto.url
            : produto.url;
        const nome = produto.name || '';
        const dim = nome.match(/(\d{2,3})\s*[xX]\s*(\d{2,3})/);
        const btu = nome.match(/(\d{4,5})\s*\.?\s*BTU/i);
        const btuK = nome.match(/(\d{1,2})\s*K\s*\.?\s*BTU/i);
        const btuDot = nome.match(/(\d{1,2})\.\s*BTU/i);
        const btuBare = nome.match(/(?<![\d.])(\d{1,2})\s*BTU/i);
        const lit = nome.match(/(\d{2,4})\s*[lL](?:itros?)?\b/);
        let dimensao = null;
        if (dim) dimensao = `${dim[1]}x${dim[2]}`;
        else if (btu) dimensao = `${btu[1]} BTU`;
        else if (btuK) dimensao = `${+btuK[1] * 1000} BTU`;
        else if (btuDot) dimensao = `${+btuDot[1] * 1000} BTU`;
        else if (btuBare) dimensao = `${+btuBare[1] * 1000} BTU`;
        else if (lit) dimensao = `${lit[1]}L`;
        const entry = {
          name: produto.name,
          url,
          dimensao,
          preco_normal: offer.initial_price || precoFinal,
          preco_desconto: offer.discount_ati || 0,
          preco_final: precoFinal,
        };
        if (!found[pid] || entry.preco_final < found[pid].preco_final) {
          found[pid] = entry;
        }
      });
    });
  });

  const loja = prompt('Nome da loja atual? (ex: Alta de Lisboa)');
  if (loja === null) return;
  const resultado = { loja, produtos: found };
  const texto = JSON.stringify(resultado);
  const n = Object.keys(found).length;
  navigator.clipboard.writeText(texto).then(() => {
    alert('Copiado! ' + n + ' produtos. Cola no chat.');
  }).catch(() => {
    prompt('Não consegui copiar sozinho -- copia isto (Ctrl+C) e cola no chat:', texto);
  });
})();
