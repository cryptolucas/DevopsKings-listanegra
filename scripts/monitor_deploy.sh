#!/usr/bin/env bash
# Monitorea /health cada segundo durante un despliegue en Elastic Beanstalk.
# Equivalente a monitor_deploy.ps1 para Mac/Linux (compatible con bash 3.2).
#
# Uso:
#   ./scripts/monitor_deploy.sh <url-del-ambiente> <version-objetivo> [respuestas-seguidas=30]
#   ./scripts/monitor_deploy.sh http://listanegra-env.eba-xxxx.us-east-1.elasticbeanstalk.com 1.0.1

set -u

if [ $# -lt 2 ]; then
  echo "Uso: $0 <url> <version-objetivo> [respuestas-seguidas=30]" >&2
  exit 1
fi

url="${1%/}"
target="$2"
stop_after="${3:-30}"
case "$url" in */health) ;; *) url="$url/health" ;; esac

root="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$root/evidencias"
log="$root/evidencias/${target}-$(date +%Y%m%d-%H%M%S).log"
data="$(mktemp)"

red=$'\033[31m'; green=$'\033[32m'; yellow=$'\033[33m'; cyan=$'\033[36m'; reset=$'\033[0m'

out() { printf '%s%s%s\n' "${2:-}" "$1" "$reset"; printf '%s\n' "$1" >> "$log"; }

summary() {
  trap - INT TERM
  end=$(date +%s)
  out ""
  out "================ RESUMEN ================" "$cyan"
  out "Duracion del monitoreo: $((end - start)) s"
  # data: elapsed<TAB>code<TAB>version<TAB>host
  awk -F'\t' -v target="$target" -v stop="$stop_after" '
    { total++
      if ($2 != 200) { fail++; streak = 0; last_non = $1; if (!ff) ff = $1 "s"; lf = $1; next }
      ver[$3]++; hst[$4]++
      if ($3 == target) { if (ft == "") ft = $1; neu[$4] = 1; streak++ }
      else { if ($4 != "-") old[$4] = 1; last_non = $1; streak = 0 } }
    END {
      printf "Solicitudes: %d   Exitosas: %d   Fallidas: %d\n", total, total - fail, fail
      if (ft != "") printf "Primera respuesta con %s: t=%ss\n", target, ft
      else printf "Nunca respondio la version %s\n", target
      if (streak >= stop) printf "100%% en %s desde: t=%ds (%d min %d s)\n", target, last_non, int(last_non / 60), last_non % 60
      else print "Monitoreo detenido antes de confirmar 100% de la nueva version."
      if (fail) printf "Downtime observado: %d solicitudes fallidas entre t=%s y t=%ss (ventana de %d s)\n", fail, ff, lf, lf - ff + 1
      else print "Downtime observado: ninguno (0 fallos)"
      print "Respuestas por version:"; for (k in ver) printf "  %-10s %d\n", k, ver[k]
      print "Respuestas por host:";    for (k in hst) printf "  %-20s %d\n", k, hst[k]
      o = ""; for (k in old) o = o (o ? ", " : "") k
      n = ""; reused = 0; nn = 0
      for (k in neu) { n = n (n ? ", " : "") k; nn++; if (k in old) reused++ }
      printf "Hosts con version anterior: %s\n", (o ? o : "-")
      printf "Hosts con version %s: %s\n", target, (n ? n : "-")
      if (nn) {
        if (o == "") print "Literal d: no se vieron hosts con la version anterior; no se puede comparar."
        else if (reused == nn) print "Literal d: la nueva version corre sobre las MISMAS instancias iniciales."
        else if (reused == 0) print "Literal d: la nueva version corre sobre instancias NUEVAS."
        else print "Literal d: mezcla de instancias reutilizadas y nuevas."
      }
    }' "$data" | while IFS= read -r l; do out "$l"; done
  out "El tiempo oficial (literal c) es el de la pestana Events: 'Environment update is starting' -> 'completed successfully'."
  out "Log guardado en $log" "$cyan"
  rm -f "$data"
  exit 0
}
trap summary INT TERM

start=$(date +%s)
out "Monitor de despliegue - $(date '+%Y-%m-%d %H:%M:%S')"
out "URL: $url | version objetivo: $target | fin tras $stop_after respuestas seguidas"
out "Log: $log"
out ""

streak=0
while [ "$streak" -lt "$stop_after" ]; do
  elapsed=$(( $(date +%s) - start ))
  resp="$(curl -s -m 3 -w $'\n%{http_code}' "$url" 2>/dev/null)"
  code="$(printf '%s' "$resp" | tail -n1)"
  body="$(printf '%s' "$resp" | sed '$d')"
  version="$(printf '%s' "$body" | grep -o '"version": *"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/')"
  host="$(printf '%s' "$body" | grep -o '"host": *"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/')"
  [ -z "$code" ] || [ "$code" = "000" ] && code="ERR"
  version="${version:--}"; host="${host:--}"

  printf '%s\t%s\t%s\t%s\n' "$elapsed" "$code" "$version" "$host" >> "$data"
  line="$(printf '%s  t=%5ss  HTTP %3s  version=%-8s host=%s' "$(date +%H:%M:%S)" "$elapsed" "$code" "$version" "$host")"

  if [ "$code" != "200" ]; then
    streak=0; out "$line" "$red"
  elif [ "$version" = "$target" ]; then
    streak=$((streak + 1)); out "$line" "$green"
  else
    streak=0; out "$line" "$yellow"
  fi
  sleep 1
done
summary
