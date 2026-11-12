import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { z } from 'zod';

const reviewSchema = z.object({
  id: z.string(),
  authorId: z.string(),
  rating: z.number().int().min(1).max(5),
  body: z.string(),
  createdAt: z.string().datetime(),
});

const authorSchema = z.object({
  id: z.string(),
  displayName: z.string(),
  avatarUrl: z.string().url(),
});

const translationSchema = z.object({ translation: z.string() });

type Review = z.infer<typeof reviewSchema>;
type Author = z.infer<typeof authorSchema>;
type ReviewWithAuthor = Review & { author: Author | undefined };

type TranslationRequest = { reviewId: string; target: string };

const translationKey = (reviewId: string, target: string) => `${reviewId}:${target}`;

type ProductReviewsProps = {
  productId: string;
  targetLanguage: string;
};

async function getJson<T>(url: string, schema: z.ZodType<T>, signal?: AbortSignal): Promise<T> {
  const res = await fetch(url, { signal });
  if (!res.ok) {
    throw new Error(`GET ${url} failed with ${res.status}`);
  }
  return schema.parse(await res.json());
}

async function fetchReviews(productId: string, signal: AbortSignal): Promise<ReviewWithAuthor[]> {
  const id = encodeURIComponent(productId);
  const reviews = await getJson(`/api/products/${id}/reviews`, z.array(reviewSchema), signal);
  if (reviews.length === 0) {
    return [];
  }
  const ids = [...new Set(reviews.map((r) => r.authorId))].map(encodeURIComponent).join(',');
  const authors = await getJson(`/api/users?ids=${ids}`, z.array(authorSchema), signal);
  const byId = new Map(authors.map((a) => [a.id, a]));
  return reviews.map((review) => ({ ...review, author: byId.get(review.authorId) }));
}

// The server holds the translation provider key; the browser only talks to our API.
async function translateReview(reviewId: string, target: string): Promise<string> {
  const res = await fetch(`/api/reviews/${encodeURIComponent(reviewId)}/translate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target }),
  });
  if (!res.ok) {
    throw new Error(`translation failed with ${res.status}`);
  }
  return translationSchema.parse(await res.json()).translation;
}

export function ProductReviews({ productId, targetLanguage }: ProductReviewsProps) {
  const [translated, setTranslated] = useState<Record<string, string>>({});

  const reviewsQuery = useQuery({
    queryKey: ['product-reviews', productId],
    queryFn: ({ signal }) => fetchReviews(productId, signal),
  });

  const translation = useMutation({
    mutationFn: ({ reviewId, target }: TranslationRequest) => translateReview(reviewId, target),
    onSuccess: (text, { reviewId, target }) =>
      setTranslated((prev) => ({ ...prev, [translationKey(reviewId, target)]: text })),
  });

  if (reviewsQuery.isPending) {
    return <p aria-busy="true">Loading reviews…</p>;
  }

  if (reviewsQuery.isError) {
    return (
      <p role="alert">
        Reviews could not be loaded.{' '}
        <button type="button" onClick={() => reviewsQuery.refetch()}>
          Try again
        </button>
      </p>
    );
  }

  const reviews = reviewsQuery.data;
  if (reviews.length === 0) {
    return <p>No reviews yet. Be the first to review this product.</p>;
  }

  return (
    <section aria-labelledby="reviews-heading">
      <h2 id="reviews-heading">Customer reviews ({reviews.length})</h2>
      {translation.isError && <p role="alert">Translation is unavailable right now.</p>}
      <ul className="review-list">
        {reviews.map((review) => (
          <li key={review.id} className="review">
            <header className="review__header">
              {review.author && (
                <img src={review.author.avatarUrl} alt="" width={32} height={32} />
              )}
              <span className="review__author">
                {review.author?.displayName ?? 'Former customer'}
              </span>
              <span className="review__rating" role="img" aria-label={`${review.rating} out of 5 stars`}>
                {'★'.repeat(review.rating)}
              </span>
              <time dateTime={review.createdAt}>
                {new Date(review.createdAt).toLocaleDateString()}
              </time>
            </header>
            <p className="review__body">{translated[translationKey(review.id, targetLanguage)] ?? review.body}</p>
            <button
              type="button"
              className="review__translate"
              disabled={translation.isPending && translation.variables?.reviewId === review.id}
              onClick={() => translation.mutate({ reviewId: review.id, target: targetLanguage })}
            >
              Translate
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
