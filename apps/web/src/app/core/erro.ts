import { HttpErrorResponse } from '@angular/common/http';

/**
 * A frase que a tela mostra quando um pedido falha.
 *
 * O servidor já explica em português o que recusou (`detail`); a tela só cai na
 * mensagem padrão quando não há explicação. Sem rede e excesso de pedidos têm
 * frase própria, porque "tente de novo" sozinho não ajuda nesses dois casos.
 */
export function mensagemDoErro(falha: unknown, padrao: string): string {
  const resposta = falha instanceof HttpErrorResponse ? falha : null;
  const status = resposta?.status ?? (falha as { status?: number } | null)?.status;

  if (status === 0) {
    return 'Sem conexão com a internet. Confira o sinal e tente de novo.';
  }
  if (status === 429) {
    const espera = resposta?.headers?.get('Retry-After');
    return espera
      ? `Muitas tentativas seguidas. Tente de novo em ${espera} s.`
      : 'Muitas tentativas seguidas. Espere um pouco e tente de novo.';
  }

  const detalhe: unknown = (falha as { error?: { detail?: unknown } } | null)?.error?.detail;
  if (typeof detalhe === 'string' && detalhe.trim()) {
    return frase(detalhe.trim());
  }
  return padrao;
}

/** "a pausa precisa terminar no futuro" → "A pausa precisa terminar no futuro." */
function frase(texto: string): string {
  const inicio = texto.charAt(0).toUpperCase() + texto.slice(1);
  return /[.!?]$/.test(inicio) ? inicio : `${inicio}.`;
}
