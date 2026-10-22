/* Beispielimplementierung der Bibliothek "wsat" fuer die CLI-Demo.
 * Die Funktion summiert n ganze Zahlen; init/fini zeigen den Lebenszyklus.
 *
 * Der Generator (sl gen) erzeugt einen Header mit dem Makro SL_EXPORT. Dessen
 * Dateiname wird von demo.py im Ordner gen/ gesucht; fehlt er, wird SL_EXPORT
 * leer definiert (dann muessen die Symbole anders sichtbar gemacht werden).
 */
#if defined(__has_include)
#  if __has_include("wsat.h")
#    include "wsat.h"
#  endif
#endif

#ifndef SL_EXPORT
#  define SL_EXPORT
#endif

static int g_initialised = 0;

SL_EXPORT int wsat_init(void) {
    g_initialised = 1;
    return 0; /* 0 = Erfolg */
}

SL_EXPORT int wsat_fini(void) {
    g_initialised = 0;
    return 0;
}

SL_EXPORT int wsat_solve(const int *xs, unsigned int n) {
    int sum = 0;
    unsigned int i;
    if (!g_initialised) return -1;
    for (i = 0; i < n; ++i) sum += xs[i];
    return sum;
}
