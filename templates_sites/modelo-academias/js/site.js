/* Modelo de academia: slides do topo, contadores, menu do celular, carrossel e horário de hoje. */
(() => {
  const semMovimento = matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Cabeçalho ganha fundo ao rolar
  const topo = document.getElementById("topo");
  const aoRolar = () => topo.classList.toggle("rolou", scrollY > 40);
  addEventListener("scroll", aoRolar, { passive: true }); aoRolar();

  // Menu do celular
  const menu = document.getElementById("menu"), botaoMenu = document.getElementById("abrir-menu");
  botaoMenu.addEventListener("click", () => {
    const aberto = menu.classList.toggle("aberto");
    botaoMenu.setAttribute("aria-expanded", aberto);
  });
  menu.querySelectorAll("a").forEach((a) => a.addEventListener("click", () => menu.classList.remove("aberto")));

  // Slides do topo com barrinhas de progresso
  const slides = [...document.querySelectorAll(".slide")];
  const barras = [...document.querySelectorAll("#progresso button")];
  const TEMPO = 6000;
  let atual = 0, timer;
  function mostrar(i) {
    slides[atual].classList.remove("ativo");
    atual = (i + slides.length) % slides.length;
    slides[atual].classList.add("ativo");
    barras.forEach((b, n) => {
      b.classList.remove("ativo", "feito");
      void b.offsetWidth; // reinicia a animação da barra
      if (n < atual) b.classList.add("feito");
      if (n === atual) b.classList.add("ativo");
    });
    clearTimeout(timer);
    if (!semMovimento) timer = setTimeout(() => mostrar(atual + 1), TEMPO);
  }
  if (slides.length > 1) {
    document.documentElement.style.setProperty("--tempo", TEMPO + "ms");
    barras.forEach((b, n) => b.addEventListener("click", () => mostrar(n)));
    mostrar(0);
  }

  // Contadores animados quando aparecem na tela
  const formatar = (v, casas) => v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
  const contar = (el) => {
    const texto = el.dataset.contar, alvo = parseFloat(texto.replace(".", "").replace(",", "."));
    const casas = texto.includes(",") ? 1 : 0;
    if (isNaN(alvo) || semMovimento) return;
    const inicio = performance.now(), dur = 1400;
    const passo = (t) => {
      const p = Math.min((t - inicio) / dur, 1), e = 1 - Math.pow(1 - p, 3);
      el.textContent = formatar(alvo * e, casas);
      if (p < 1) requestAnimationFrame(passo); else el.textContent = texto;
    };
    requestAnimationFrame(passo);
  };

  // Revela seções e dispara contadores ao rolar
  const observador = new IntersectionObserver((itens) => {
    itens.forEach((it) => {
      if (!it.isIntersecting) return;
      it.target.classList.add("visivel");
      if (it.target.dataset.contar) contar(it.target);
      observador.unobserve(it.target);
    });
  }, { threshold: 0.2 });
  document.querySelectorAll(".revelar, [data-contar]").forEach((el) => observador.observe(el));

  // Setas do carrossel da estrutura
  const carrossel = document.getElementById("carrossel");
  document.querySelectorAll("[data-carrossel]").forEach((b) => b.addEventListener("click", () => {
    carrossel.scrollBy({ left: Number(b.dataset.carrossel) * carrossel.clientWidth * 0.8, behavior: semMovimento ? "auto" : "smooth" });
  }));

  // Destaca o horário de hoje
  const hoje = new Date().toLocaleDateString("pt-BR", { weekday: "long" }).toLowerCase();
  document.querySelectorAll("#horarios li").forEach((li) => { if (li.dataset.dia.startsWith(hoje.split("-")[0])) li.classList.add("hoje"); });
})();
