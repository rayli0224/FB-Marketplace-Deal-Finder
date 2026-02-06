"use client";

export interface Listing {
  title: string;
  price: number;
  location: string;
  url: string;
  dealScore: number;
}

export interface SearchResultsTableProps {
  listings: Listing[];
  scannedCount: number;
  onDownloadCSV: () => void;
  onReset: () => void;
}

/**
 * Determines the color class for a deal score based on its value.
 * Returns green for excellent deals (20%+), accent for good deals (10-19%), and muted for others.
 */
/**
 * Determines the color class for a deal score based on its value.
 * Returns green for excellent deals (20%+), accent for good deals (10-19%), and muted for others.
 */
function getDealScoreColorClass(dealScore: number): string {
  if (dealScore >= 20) return "text-green-500";
  if (dealScore >= 10) return "text-accent";
  return "text-muted-foreground";
}

/**
 * Results table component displaying search results in a scrollable table.
 * Shows listing details including title, price, location, deal score, and link.
 * Includes header with result counts and action buttons for CSV export and new search.
 */
export function SearchResultsTable({ listings, scannedCount, onDownloadCSV, onReset }: SearchResultsTableProps) {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-mono text-lg font-bold text-foreground">
            HEIST COMPLETE!
          </h2>
          <p className="font-mono text-xs text-muted-foreground">
            Found {listings.length} treasures from {scannedCount} scanned
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onDownloadCSV}
            className="border-2 border-primary bg-transparent px-3 py-2 font-mono text-xs font-bold text-primary transition-all hover:bg-primary hover:text-primary-foreground"
          >
            EXPORT CSV
          </button>
          <button
            type="button"
            onClick={onReset}
            className="border-2 border-accent bg-accent px-3 py-2 font-mono text-xs font-bold text-accent-foreground transition-all hover:bg-transparent hover:text-accent"
          >
            NEW SEARCH
          </button>
        </div>
      </div>

      {listings.length > 0 ? (
        <div className="max-h-[60vh] overflow-auto border border-border">
          <table className="w-full border-collapse font-mono text-sm">
            <thead className="sticky top-0 bg-secondary">
              <tr className="border-b border-border text-left">
                <th className="px-3 py-2 text-xs text-muted-foreground">TITLE</th>
                <th className="px-3 py-2 text-xs text-muted-foreground">PRICE</th>
                <th className="px-3 py-2 text-xs text-muted-foreground">LOCATION</th>
                <th className="px-3 py-2 text-xs text-muted-foreground">DEAL %</th>
                <th className="px-3 py-2 text-xs text-muted-foreground">LINK</th>
              </tr>
            </thead>
            <tbody>
              {listings.map((listing, index) => (
                <tr 
                  key={index} 
                  className="border-b border-border/50 hover:bg-secondary/50 transition-colors"
                >
                  <td className="px-3 py-2 max-w-[300px] truncate" title={listing.title}>
                    {listing.title}
                  </td>
                  <td className="px-3 py-2 text-primary font-bold">
                    ${listing.price.toFixed(2)}
                  </td>
                  <td className="px-3 py-2 text-muted-foreground max-w-[150px] truncate" title={listing.location}>
                    {listing.location}
                  </td>
                  <td className="px-3 py-2">
                    {listing.dealScore > 0 ? (
                      <span className={`font-bold ${getDealScoreColorClass(listing.dealScore)}`}>
                        {listing.dealScore}%
                      </span>
                    ) : (
                      <span className="text-muted-foreground/50">--</span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <a 
                      href={listing.url} 
                      target="_blank" 
                      rel="noopener noreferrer"
                      className="text-primary hover:underline"
                    >
                      VIEW →
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="border border-border bg-secondary p-8 text-center">
          <p className="font-mono text-muted-foreground">No listings found matching your criteria.</p>
        </div>
      )}
    </div>
  );
}

