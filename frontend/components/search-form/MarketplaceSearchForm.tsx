"use client";

import { type UseFormRegister, type FieldErrors, type UseFormHandleSubmit } from "react-hook-form";
import { type FormData as ValidationFormData } from "@/lib/validation";
import { TreasureIcon } from "@/lib/icons";
import { FormInputField } from "@/components/search-form/FormInputField";

export interface MarketplaceSearchFormProps {
  register: UseFormRegister<ValidationFormData>;
  errors: FieldErrors<ValidationFormData>;
  isValid: boolean;
  handleSubmit: UseFormHandleSubmit<ValidationFormData>;
}

/**
 * Search form component for entering marketplace search parameters.
 * Includes fields for query, zip code, radius, and threshold with validation.
 * Submit button is disabled until all fields are valid.
 */
export function MarketplaceSearchForm({ register, errors, isValid, handleSubmit }: MarketplaceSearchFormProps) {
  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div className="mb-4 font-mono text-xs text-muted-foreground">
        <span className="text-primary">{">"}</span> Enter target parameters, matey...
      </div>

      <FormInputField
        label="TARGET_QUERY"
        id="query"
        type="text"
        placeholder="e.g. iPhone 13 Pro"
        register={register}
        required
        error={errors.query?.message}
        icon={<TreasureIcon className="text-accent" />}
      />

      <FormInputField
        label="PORT_CODE"
        id="zipCode"
        type="text"
        placeholder="e.g. 10001"
        register={register}
        pattern="[0-9]{5}"
        required
        error={errors.zipCode?.message}
        icon={<span className="text-accent">@</span>}
      />

      <div className="grid grid-cols-2 gap-4">
        <FormInputField
          label="RAID_RADIUS"
          id="radius"
          type="number"
          placeholder="25"
          register={register}
          min={1}
          max={500}
          required
          error={errors.radius?.message}
          suffix="mi"
        />

        <FormInputField
          label="STEAL_THRESHOLD"
          id="threshold"
          type="number"
          placeholder="80"
          register={register}
          min={0}
          max={100}
          required
          error={errors.threshold?.message}
          suffix="%"
          tooltip="Max % of eBay average price. Example: 80% = only show listings priced at 80% of eBay market value or less"
        />
      </div>

      <button
        type="submit"
        disabled={!isValid}
        className={`group mt-2 w-full border-2 px-4 py-3 font-mono text-sm font-bold uppercase tracking-wide transition-all ${
          isValid
            ? "border-primary bg-primary text-primary-foreground hover:bg-transparent hover:text-primary cursor-pointer"
            : "border-muted bg-muted text-muted-foreground cursor-not-allowed opacity-50"
        }`}
      >
        <span className={`inline-block transition-transform ${isValid ? "group-hover:translate-x-1" : ""}`}>
          {">>>"} BEGIN HEIST {"<<<"}
        </span>
      </button>
    </form>
  );
}

