/** Caminho que grava o que mandaram desenhar, no lugar do Path2D do navegador. */
export class CaminhoGravado {
  readonly chamadas: Array<[string, ...number[]]> = [];
  moveTo(x: number, y: number) { this.chamadas.push(["moveTo", x, y]); }
  lineTo(x: number, y: number) { this.chamadas.push(["lineTo", x, y]); }
  arc(cx: number, cy: number, r: number, a0: number, a1: number) {
    this.chamadas.push(["arc", cx, cy, r, a0, a1]);
  }
  bezierCurveTo(x1: number, y1: number, x2: number, y2: number,
                x3: number, y3: number) {
    this.chamadas.push(["bezierCurveTo", x1, y1, x2, y2, x3, y3]);
  }
  closePath() { this.chamadas.push(["closePath"]); }

  /** Quantos traços começaram: um `moveTo` ou um `arc` por entidade. */
  get inicios(): number {
    return this.chamadas.filter((c) => c[0] === "moveTo" || c[0] === "arc").length;
  }
}

/** Contexto 2D de mentira, que guarda os caminhos traçados e os textos. */
export class ContextoGravado {
  lineWidth = 1;
  strokeStyle = "#000";
  fillStyle = "#000";
  font = "";
  readonly tracados: CaminhoGravado[] = [];
  readonly textos: Array<{ texto: string; x: number; y: number }> = [];
  readonly estilos: string[] = [];

  save() {}
  restore() {}
  translate(_x: number, _y: number) {}
  rotate(_a: number) {}
  clearRect(_x: number, _y: number, _w: number, _h: number) {}
  fillRect(_x: number, _y: number, _w: number, _h: number) {}
  fillText(t: string, x: number, y: number) { this.textos.push({ texto: t, x, y }); }
  stroke(c: CaminhoGravado) {
    this.tracados.push(c);
    this.estilos.push(this.strokeStyle);
  }

  /** Total de entidades traçadas, somando todos os caminhos. */
  get inicios(): number {
    return this.tracados.reduce((soma, c) => soma + c.inicios, 0);
  }
}
