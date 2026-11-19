import { useEffect, useId, useRef, useState } from 'react'
import { searchPlaces } from '../lib/api'
import type { Place } from '../lib/types'

interface Props {
  label: string
  placeholder: string
  value: Place | null
  onChange: (place: Place | null) => void
  /** Text typed but not yet matched to a place; the form resolves it on submit. */
  onTextChange: (text: string) => void
}

export default function PlaceInput({ label, placeholder, value, onChange, onTextChange }: Props) {
  const id = useId()
  const [text, setText] = useState(value?.label ?? '')
  const [options, setOptions] = useState<Place[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const [loading, setLoading] = useState(false)
  const skipSearch = useRef(false)

  // Keep the box in step when the parent swaps origin and destination.
  useEffect(() => {
    if (value && value.label !== text) {
      skipSearch.current = true
      setText(value.label)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  useEffect(() => {
    if (skipSearch.current) {
      skipSearch.current = false
      return
    }
    const query = text.trim()
    if (query.length < 2 || query === value?.label) {
      setOptions([])
      return
    }
    const controller = new AbortController()
    const timer = setTimeout(() => {
      setLoading(true)
      searchPlaces(query, controller.signal)
        .then((results) => {
          setOptions(results)
          setActive(0)
          setOpen(true)
        })
        .catch(() => undefined)
        .finally(() => setLoading(false))
    }, 220)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text])

  const choose = (place: Place) => {
    skipSearch.current = true
    setText(place.label)
    setOpen(false)
    setOptions([])
    onChange(place)
    onTextChange(place.label)
  }

  return (
    <div className="field place">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-controls={`${id}-list`}
        aria-autocomplete="list"
        autoComplete="off"
        spellCheck={false}
        placeholder={placeholder}
        value={text}
        onChange={(event) => {
          setText(event.target.value)
          onTextChange(event.target.value)
          if (value) onChange(null)
        }}
        onFocus={() => options.length > 0 && setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onKeyDown={(event) => {
          if (!open || options.length === 0) return
          if (event.key === 'ArrowDown') {
            event.preventDefault()
            setActive((active + 1) % options.length)
          } else if (event.key === 'ArrowUp') {
            event.preventDefault()
            setActive((active - 1 + options.length) % options.length)
          } else if (event.key === 'Enter') {
            event.preventDefault()
            choose(options[active])
          } else if (event.key === 'Escape') {
            setOpen(false)
          }
        }}
      />
      {loading && <span className="spinner small" aria-hidden />}
      {open && options.length > 0 && (
        <ul className="suggestions" id={`${id}-list`} role="listbox">
          {options.map((option, index) => (
            <li
              key={`${option.lat},${option.lon}`}
              role="option"
              aria-selected={index === active}
              className={index === active ? 'active' : ''}
              onMouseDown={(event) => {
                event.preventDefault()
                choose(option)
              }}
              onMouseEnter={() => setActive(index)}
            >
              {option.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
