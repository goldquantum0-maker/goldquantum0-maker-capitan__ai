export function fmtUsd(n) {
  return n.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: n < 1 ? 4 : 2,
  });
}

export function fmtNum(n) {
  return n.toLocaleString('en-US', {
    maximumFractionDigits: n < 1 ? 6 : 2,
  });
}

export function escapeHtml(s) {
  return s?.replace(/</g, '&lt;') || '';
}

export function formatMarkdown(t) {
  return t
    ?.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    ?.replace(/\*(.*?)\*/g, '<em>$1</em>')
    ?.replace(/\n/g, '<br>') || '';
}