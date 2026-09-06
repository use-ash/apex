// Wrap-tolerant terminal link provider.
//
// xterm's WebLinksAddon stitches a URL across rows only when the buffer marks
// the continuation row `isWrapped`. TUIs that lay out their own text (Ink, so
// Claude Code) wrap by emitting a newline per row, so a long OAuth URL becomes
// N unrelated rows: row 1 matches as a truncated link, rows 2..N match nothing.
// This provider also joins rows that merely *look* wrapped — the previous row
// fills the last column and the next row starts without whitespace.
(function (global) {
  var LINK_RE = /(https?|HTTPS?):[/]{2}[^\s"'!*(){}|\\\^<>`]*[^\s"':,.!?{}|\\\^~\[\]`()<>]/g;
  var MAX_ROWS = 16;

  function installApexTermLinks(term, openLink) {
    function line(y) {
      return term.buffer.active.getLine(y);
    }

    function flowsInto(y) {
      var cur = line(y), next = line(y + 1);
      if (!cur || !next) return false;
      if (next.isWrapped) return true;
      var text = cur.translateToString(false);
      if (text.length < term.cols || text.charAt(term.cols - 1) === ' ') return false;
      var head = next.translateToString(true);
      return head.length > 0 && head.charAt(0) !== ' ';
    }

    term.registerLinkProvider({
      provideLinks: function (row, callback) {
        var cols = term.cols;
        var abs = term.buffer.active.viewportY + row - 1;
        if (!line(abs)) return callback(undefined);

        var top = abs, bottom = abs;
        while (top > 0 && abs - top < MAX_ROWS && flowsInto(top - 1)) top--;
        while (bottom - abs < MAX_ROWS && flowsInto(bottom)) bottom++;

        var joined = '';
        for (var y = top; y <= bottom; y++) joined += line(y).translateToString(false);

        var rowStart = (abs - top) * cols;
        var rowEnd = rowStart + cols - 1;
        var links = [];
        LINK_RE.lastIndex = 0;
        var m;
        while ((m = LINK_RE.exec(joined)) !== null) {
          var from = m.index, to = m.index + m[0].length - 1;
          if (to < rowStart || from > rowEnd) continue;
          var a = Math.max(from, rowStart), b = Math.min(to, rowEnd);
          links.push({
            text: m[0],
            range: {
              start: { x: (a % cols) + 1, y: row },
              end: { x: (b % cols) + 1, y: row },
            },
            activate: (function (uri) {
              return function () { openLink(uri); };
            })(m[0]),
          });
        }
        callback(links.length ? links : undefined);
      },
    });
  }

  global.installApexTermLinks = installApexTermLinks;
})(typeof window !== 'undefined' ? window : this);
