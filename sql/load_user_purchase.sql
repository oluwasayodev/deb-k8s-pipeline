CREATE SCHEMA ecommerce;
CREATE TABLE IF NOT EXIST ecommerce.user_purchase (
    invoice_no VARCHAR(10),
    stock_code VARCHAR(20),
    description VARCHAR(1000),
    quantity INT,
    invoice_date TIMESTAMP,
    unit_price NUMERIC(8, 3),
    customer_id VARCHAR(20),
    country VARCHAR(20)
)