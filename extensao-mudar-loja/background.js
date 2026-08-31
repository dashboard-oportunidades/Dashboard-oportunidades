// Extensao "Mudar Loja - Leroy Merlin"
//
// Ao clicar no icone da extensao, avanca para a loja seguinte da lista
// (gerada a partir do config.json) e escreve o cookie 'store' via
// chrome.cookies.set() -- API do browser, nao da pagina, por isso
// consegue escrever cookies HttpOnly (o que um bookmarklet nunca conseguiria).
//
// Se acrescentares lojas novas ao config.json, volta a gerar este ficheiro.

const LOJAS = {
  "Albufeira": 4,
  "Alfragide": 5,
  "Almada": 3,
  "Alta de Lisboa": 17,
  "Alverca": 71,
  "Amadora": 7,
  "Aveiro": 14,
  "Barcelos": 69,
  "Barreiro": 55,
  "Braga": 11,
  "Braganca": 59,
  "Caldas da Rainha": 57,
  "Carcavelos": 70,
  "Cascais": 38,
  "Castelo Branco": 63,
  "Chaves": 67,
  "Coimbra": 9,
  "Colombo": 39,
  "Covilha": 32,
  "Evora": 46,
  "Figueira da Foz": 56,
  "Gaia": 10,
  "Gondomar": 1,
  "Guarda": 54,
  "Guimaraes": 33,
  "Leiria": 13,
  "Loule": 12,
  "Loures": 44,
  "Mafra": 58,
  "Maia": 8,
  "Matosinhos": 6,
  "Montijo": 34,
  "Oeiras": 60,
  "Penafiel": 51,
  "Portimao": 19,
  "Sacavem": 65,
  "Santa Maria da Feira": 52,
  "Santarem": 18,
  "Setubal": 36,
  "Sintra": 2,
  "Telheiras": 72,
  "Torres Novas": 61,
  "Torres Vedras": 31,
  "Viana do Castelo": 47,
  "Viseu": 43
};

const NOMES = Object.keys(LOJAS);
const DOMINIO = '.leroymerlin.pt';
const URL_BASE = 'https://www.leroymerlin.pt/';

async function mostrarAlerta(tabId, texto) {
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      func: (msg) => alert(msg),
      args: [texto],
    });
  } catch (e) {
    // separador pode nao ser do leroymerlin.pt -- sem problema, o cookie
    // ja foi escrito na mesma.
  }
}

async function proximaLoja() {
  const guardado = await chrome.storage.local.get('idx');
  const idxAnterior = typeof guardado.idx === 'number' ? guardado.idx : -1;
  const idx = (idxAnterior + 1) % NOMES.length;
  await chrome.storage.local.set({ idx });

  const nome = NOMES[idx];
  const id = LOJAS[nome];
  const hoje = new Date().toISOString().slice(0, 10).replace(/-/g, '');

  await chrome.cookies.set({
    url: URL_BASE, domain: DOMINIO, path: '/',
    name: 'store', value: `store=${id}|dateContext=${hoje}`,
  });
  await chrome.cookies.set({
    url: URL_BASE, domain: DOMINIO, path: '/',
    name: 'store_id', value: String(id),
  });
  await chrome.cookies.set({
    url: URL_BASE, domain: DOMINIO, path: '/',
    name: 'lmpt_store_id', value: String(id),
  });

  const texto = `Loja ${idx + 1}/${NOMES.length}: ${nome}`;
  chrome.action.setBadgeText({ text: String(idx + 1) });
  chrome.action.setTitle({ title: texto });

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab && tab.url && tab.url.includes('leroymerlin.pt')) {
    await mostrarAlerta(tab.id, texto);
    chrome.tabs.reload(tab.id);
  }
}

chrome.action.onClicked.addListener(() => {
  proximaLoja().catch((e) => console.error('Mudar Loja:', e));
});
