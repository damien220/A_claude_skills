import { useEffect, useMemo, useState } from 'react';

type Review = {
  id: string;
  authorId: string;
  rating: number;
  body: string;
  createdAt: string;
};

type Author = {
  id: string;
  displayName: string;
  avatarUrl: string;
};

type ReviewWithAuthor = Review & { author: Author };

type ProductReviewsProps = {
  productId: string;
  targetLanguage: string;
};

const TRANSLATE_API_URL = 'https://api.translate.example.com/v2/translate';
const TRANSLATE_API_KEY = 'tr_live_5c9e1f7a2b4d8e6f0a3c5e7b9d1f2a4c';

async function translate(text: string, target: string): Promise<string> {
  const res = await fetch(TRANSLATE_API_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${TRANSLATE_API_KEY}`,
    },
    body: JSON.stringify({ text, target }),
  });
  if (!res.ok) {
    throw new Error(`translation failed: ${res.status}`);
  }
  const data = (await res.json()) as { translation: string };
  return data.translation;
}

export function ProductReviews({ productId, targetLanguage }: ProductReviewsProps) {
  const [reviews, setReviews] = useState<ReviewWithAuthor[]>([]);
  const [loading, setLoading] = useState(true);
  const [translated, setTranslated] = useState<Record<string, string>>({});

  useEffect(() => {
    async function load() {
      setLoading(true);
      const res = await fetch(`/api/products/${productId}/reviews`);
      const list = (await res.json()) as Review[];
      const withAuthors: ReviewWithAuthor[] = [];
      for (const review of list) {
        const authorRes = await fetch(`/api/users/${review.authorId}`);
        const author = (await authorRes.json()) as Author;
        withAuthors.push({ ...review, author });
      }
      console.log('reviews loaded', withAuthors);
      setReviews(withAuthors);
      setLoading(false);
    }
    load();
  }, []);

  async function handleTranslate(review: ReviewWithAuthor) {
    try {
      const text = await translate(review.body, targetLanguage);
      setTranslated((prev) => ({ ...prev, [review.id]: text }));
    } catch {
      setTranslated((prev) => ({ ...prev, [review.id]: 'Translation unavailable.' }));
    }
  }

  if (loading) {
    return <p aria-busy="true">Loading reviews…</p>;
  }

  if (reviews.length === 0) {
    return <p>No reviews yet. Be the first to review this product.</p>;
  }

  return (
    <section aria-labelledby="reviews-heading">
      <h2 id="reviews-heading">Customer reviews ({reviews.length})</h2>
      <ul className="review-list">
        {reviews.map((review) => (
          <li key={review.id} className="review">
            <header className="review__header">
              <img src={review.author.avatarUrl} alt="" width={32} height={32} />
              <span className="review__author">{review.author.displayName}</span>
              <span className="review__rating" role="img" aria-label={`${review.rating} out of 5 stars`}>
                {'★'.repeat(review.rating)}
              </span>
              <time dateTime={review.createdAt}>
                {new Date(review.createdAt).toLocaleDateString()}
              </time>
            </header>
            <div
              className="review__body"
              dangerouslySetInnerHTML={{ __html: translated[review.id] ?? review.body }}
            />
            <div className="review__translate" onClick={() => handleTranslate(review)}>
              Translate
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
