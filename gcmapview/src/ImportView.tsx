import { useRef, useState } from 'react'
import { Link } from 'react-router'
import { AlertCircle, CheckCircle2, FileJson, Loader2 } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'
import { type ImportResult, uploadJsonFg } from './gcimportApi'

export function ImportView() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [error, setError] = useState('')
  const [isUploading, setIsUploading] = useState(false)

  async function submit() {
    if (!file) return
    setIsUploading(true)
    setError('')
    setResult(null)
    try {
      setResult(await uploadJsonFg(file))
    } catch (uploadError) {
      setError(
        uploadError instanceof Error ? uploadError.message : 'Import failed',
      )
    } finally {
      setIsUploading(false)
    }
  }

  function chooseFile(selected: File | undefined) {
    setFile(selected ?? null)
    setError('')
    setResult(null)
  }

  const collections = result
    ? [
        ...new Set(result.features.map((feature) => feature.collection)),
      ]
    : []

  return (
    <Card className="mx-auto w-full max-w-xl">
      <CardHeader>
        <p className="text-xs font-medium tracking-[0.12em] text-muted-foreground uppercase">
          Feature import
        </p>
        <CardTitle className="text-2xl">Import Bane features</CardTitle>
        <CardDescription className="max-w-[52ch]">
          Upload JSON-FG, or classic GeoJSON (.geojson with CRS and objtype).
          Features are validated, transformed to EPSG:5973, and upserted by
          their Bane identity.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        <button
          type="button"
          className={cn(
            'grid w-full cursor-pointer gap-1.5 rounded-2xl border border-dashed border-border bg-muted/40 px-5 py-7 text-left transition-colors hover:border-ring hover:bg-muted/60 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 focus-visible:outline-none',
            file && 'border-solid border-primary bg-accent',
          )}
          onClick={() => inputRef.current?.click()}
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault()
            chooseFile(event.dataTransfer.files[0])
          }}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".json,.jsonfg,.geojson,application/json,application/geo+json"
            onChange={(event) => chooseFile(event.target.files?.[0])}
            hidden
          />
          <span className="inline-flex items-center gap-2 text-base font-medium text-foreground">
            <FileJson className="size-4" />
            {file ? file.name : 'Choose or drop a JSON-FG or .geojson file'}
          </span>
          <span className="text-sm text-muted-foreground">
            {file
              ? `${(file.size / 1024).toFixed(1)} KB`
              : '.jsonfg/.json for JSON-FG, .geojson for classic CRS exports'}
          </span>
        </button>

        <Button
          size="lg"
          disabled={!file || isUploading}
          onClick={submit}
        >
          {isUploading ? (
            <>
              <Loader2 data-icon="inline-start" className="animate-spin" />
              Importing…
            </>
          ) : (
            'Import dataset'
          )}
        </Button>

        {error && (
          <Alert variant="destructive">
            <AlertCircle />
            <AlertTitle>Import failed</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {result && (
          <Alert className="border-chart-1/40 bg-chart-1/10">
            <CheckCircle2 className="text-foreground" />
            <AlertTitle>
              Imported {result.total} feature
              {result.total === 1 ? '' : 's'}
            </AlertTitle>
            <AlertDescription className="space-y-3">
              <div className="flex flex-wrap gap-1.5">
                {collections.length > 0 ? (
                  collections.map((collection) => (
                    <Badge key={collection} variant="secondary">
                      {collection}
                    </Badge>
                  ))
                ) : (
                  <span>No features in the file</span>
                )}
              </div>
              {result.features.length > 0 && (
                <>
                  <Separator />
                  <code className="block rounded-md bg-background/80 px-2 py-1 font-mono text-xs text-foreground">
                    {result.features
                      .slice(0, 3)
                      .map((feature) => feature.id)
                      .join(', ')}
                    {result.features.length > 3
                      ? ` (+${result.features.length - 3} more)`
                      : ''}
                  </code>
                </>
              )}
              <Button
                variant="link"
                size="sm"
                className="h-auto px-0"
                render={<Link to="/" />}
              >
                View Bane layers on the map
              </Button>
            </AlertDescription>
          </Alert>
        )}
      </CardContent>

      <CardFooter className="text-xs text-muted-foreground">
        Upserts are idempotent by Bane business key.
      </CardFooter>
    </Card>
  )
}
