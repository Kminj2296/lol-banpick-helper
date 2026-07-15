function ChampionThumb({ src, alt, size = 24 }) {
  if (!src) return null
  return (
    <img
      src={src}
      alt={alt || ''}
      className="champion-thumb"
      style={{ width: size, height: size }}
    />
  )
}

export default ChampionThumb
